"""Mibot cmd_vel → GPIO differential drive with encoder odometry.

Subscribes:  /cmd_vel                geometry_msgs/Twist
Publishes:   /odom                    nav_msgs/Odometry
             /wheel_ticks             std_msgs/Int32MultiArray  (left, right, raw)
Broadcasts:  odom → base_link TF      (unless disabled)

Runs on the Raspberry Pi. Uses `gpiozero` for PWM (via the RPi.GPIO
backend, which on Pi 4 gives soft-PWM good enough for hobby diff-drive)
and interrupt-driven pin callbacks for the two rear quadrature encoders.

If you're developing on a laptop with no GPIO, launch with
    ros2 run mibot_drive drive_node --ros-args -p simulate:=true
and the node will publish zero encoder ticks and accept /cmd_vel without
driving any hardware. Useful for testing the rest of the stack.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from threading import Lock

import rclpy
from geometry_msgs.msg import Quaternion, TransformStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import Int32MultiArray
from tf2_ros import TransformBroadcaster


# ---------------------------------------------------------------------------
# Optional gpiozero import — lets the node be launched on a dev laptop.
# ---------------------------------------------------------------------------
try:
    from gpiozero import PWMOutputDevice, DigitalOutputDevice, DigitalInputDevice
    GPIO_AVAILABLE = True
except Exception:  # gpiozero absent, or no /dev/gpiomem
    GPIO_AVAILABLE = False


# ---------------------------------------------------------------------------
# L298N side (two motors wired in parallel per side)
# ---------------------------------------------------------------------------
class L298NSide:
    """One side of an L298N — ENx PWM + INx1/INx2 direction."""

    def __init__(self, pwm_pin: int, dir_a_pin: int, dir_b_pin: int,
                 pwm_freq: int, invert: bool = False, simulate: bool = False):
        self.invert = invert
        self.simulate = simulate

        if simulate or not GPIO_AVAILABLE:
            self._pwm = None
            self._dir_a = None
            self._dir_b = None
            return

        self._pwm = PWMOutputDevice(pwm_pin, frequency=pwm_freq)
        self._dir_a = DigitalOutputDevice(dir_a_pin)
        self._dir_b = DigitalOutputDevice(dir_b_pin)
        self.stop()

    def set(self, duty: float) -> None:
        """duty in [-1.0, 1.0]. Sign chooses direction; magnitude is PWM."""
        if self.invert:
            duty = -duty
        duty = max(-1.0, min(1.0, duty))

        if self._pwm is None:  # simulation
            return

        if duty > 0:
            self._dir_a.on()
            self._dir_b.off()
        elif duty < 0:
            self._dir_a.off()
            self._dir_b.on()
        else:
            self._dir_a.off()
            self._dir_b.off()

        self._pwm.value = abs(duty)

    def stop(self) -> None:
        if self._pwm is not None:
            self._pwm.value = 0.0
            self._dir_a.off()
            self._dir_b.off()


# ---------------------------------------------------------------------------
# Quadrature encoder (interrupt-driven)
# ---------------------------------------------------------------------------
class QuadratureEncoder:
    """Reads A/B channels on GPIO pins; keeps a signed tick counter.

    Uses gpiozero's interrupt callbacks under the hood (RPi.GPIO backend
    is fine for hobby-motor RPM). If gpiozero is unavailable the encoder
    reports zero ticks.
    """

    def __init__(self, a_pin: int, b_pin: int, invert: bool = False, simulate: bool = False):
        self.invert = invert
        self.simulate = simulate
        self._lock = Lock()
        self._ticks = 0
        self._a_state = 0
        self._b_state = 0

        if simulate or not GPIO_AVAILABLE:
            self._a = None
            self._b = None
            return

        self._a = DigitalInputDevice(a_pin, pull_up=True)
        self._b = DigitalInputDevice(b_pin, pull_up=True)
        self._a_state = int(self._a.value)
        self._b_state = int(self._b.value)
        self._a.when_activated = self._on_a_change
        self._a.when_deactivated = self._on_a_change
        self._b.when_activated = self._on_b_change
        self._b.when_deactivated = self._on_b_change

    def _on_a_change(self) -> None:
        with self._lock:
            new_a = int(self._a.value)
            # A changed. If A == B, we're going one way, else the other.
            direction = 1 if (new_a == self._b_state) else -1
            self._a_state = new_a
            self._ticks += direction

    def _on_b_change(self) -> None:
        with self._lock:
            new_b = int(self._b.value)
            direction = 1 if (new_b != self._a_state) else -1
            self._b_state = new_b
            self._ticks += direction

    def read_and_reset(self) -> int:
        with self._lock:
            ticks = self._ticks
            self._ticks = 0
        return -ticks if self.invert else ticks


# ---------------------------------------------------------------------------
# Odometry state
# ---------------------------------------------------------------------------
@dataclass
class OdomState:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    vx: float = 0.0
    wz: float = 0.0


def yaw_to_quat(yaw: float) -> Quaternion:
    q = Quaternion()
    q.z = math.sin(yaw / 2.0)
    q.w = math.cos(yaw / 2.0)
    return q


# ---------------------------------------------------------------------------
# The node
# ---------------------------------------------------------------------------
class MibotDriveNode(Node):

    def __init__(self):
        super().__init__('mibot_drive')

        # --- parameters ---------------------------------------------------
        p = self.declare_parameters(
            namespace='',
            parameters=[
                # L298N pins
                ('left_pwm_pin', 12),
                ('left_dir_a_pin', 23),
                ('left_dir_b_pin', 24),
                ('right_pwm_pin', 13),
                ('right_dir_a_pin', 27),
                ('right_dir_b_pin', 22),
                # Encoders
                ('left_encoder_a_pin', 5),
                ('left_encoder_b_pin', 6),
                ('right_encoder_a_pin', 16),
                ('right_encoder_b_pin', 26),
                ('encoder_ticks_per_revolution', 40),
                ('invert_left_encoder', False),
                ('invert_right_encoder', False),
                # Geometry
                ('wheel_radius', 0.035),
                ('wheel_separation', 0.16),
                # Motor
                ('max_linear_speed', 0.5),
                ('max_angular_speed', 3.0),
                ('pwm_frequency', 1000),
                ('min_pwm_duty', 0.15),
                # Rates
                ('control_rate_hz', 50),
                ('odom_rate_hz', 30),
                ('cmd_vel_timeout', 0.5),
                # Frames
                ('odom_frame', 'odom'),
                ('base_frame', 'base_link'),
                ('publish_odom_tf', True),
                # Dev / testing
                ('simulate', False),
            ],
        )
        self.g = {pd.name: pd.value for pd in p}
        simulate = bool(self.g['simulate']) or not GPIO_AVAILABLE
        if simulate and not self.g['simulate']:
            self.get_logger().warning(
                'gpiozero not importable — running in SIMULATE mode. '
                'Motors and encoders are stubbed.'
            )

        # --- hardware -----------------------------------------------------
        self.left_motor = L298NSide(
            self.g['left_pwm_pin'], self.g['left_dir_a_pin'], self.g['left_dir_b_pin'],
            self.g['pwm_frequency'], invert=False, simulate=simulate,
        )
        self.right_motor = L298NSide(
            self.g['right_pwm_pin'], self.g['right_dir_a_pin'], self.g['right_dir_b_pin'],
            self.g['pwm_frequency'], invert=False, simulate=simulate,
        )
        self.left_enc = QuadratureEncoder(
            self.g['left_encoder_a_pin'], self.g['left_encoder_b_pin'],
            invert=self.g['invert_left_encoder'], simulate=simulate,
        )
        self.right_enc = QuadratureEncoder(
            self.g['right_encoder_a_pin'], self.g['right_encoder_b_pin'],
            invert=self.g['invert_right_encoder'], simulate=simulate,
        )

        # --- state --------------------------------------------------------
        self.odom = OdomState()
        self.cmd_linear = 0.0
        self.cmd_angular = 0.0
        self.last_cmd_time = self.get_clock().now()
        self.last_odom_time = self.get_clock().now()
        self._left_ticks_total = 0
        self._right_ticks_total = 0

        # --- ROS interfaces ----------------------------------------------
        self.create_subscription(Twist, 'cmd_vel', self.cmd_vel_cb, 10)
        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)
        self.ticks_pub = self.create_publisher(Int32MultiArray, 'wheel_ticks', 10)
        self.tf_broadcaster = TransformBroadcaster(self)

        self.create_timer(1.0 / self.g['control_rate_hz'], self.control_step)
        self.create_timer(1.0 / self.g['odom_rate_hz'], self.odom_step)

        self.get_logger().info(
            f"mibot_drive up (simulate={simulate}) — "
            f"wheel_radius={self.g['wheel_radius']} m, "
            f"wheel_sep={self.g['wheel_separation']} m, "
            f"ticks/rev={self.g['encoder_ticks_per_revolution']}"
        )

    # ---------- callbacks ------------------------------------------------
    def cmd_vel_cb(self, msg: Twist) -> None:
        self.cmd_linear = float(msg.linear.x)
        self.cmd_angular = float(msg.angular.z)
        self.last_cmd_time = self.get_clock().now()

    # ---------- control loop --------------------------------------------
    def control_step(self) -> None:
        # Watchdog: stop if we haven't heard from cmd_vel in a while.
        now = self.get_clock().now()
        dt = (now - self.last_cmd_time).nanoseconds * 1e-9
        if dt > self.g['cmd_vel_timeout']:
            self.left_motor.stop()
            self.right_motor.stop()
            return

        # Cap commanded speeds.
        v = max(-self.g['max_linear_speed'],
                min(self.g['max_linear_speed'], self.cmd_linear))
        w = max(-self.g['max_angular_speed'],
                min(self.g['max_angular_speed'], self.cmd_angular))

        # Diff-drive inverse kinematics.
        v_left  = v - w * self.g['wheel_separation'] / 2.0
        v_right = v + w * self.g['wheel_separation'] / 2.0

        # m/s → normalised duty in [-1, 1].
        duty_left  = v_left  / self.g['max_linear_speed']
        duty_right = v_right / self.g['max_linear_speed']
        duty_left  = self._apply_deadband(duty_left)
        duty_right = self._apply_deadband(duty_right)

        self.left_motor.set(duty_left)
        self.right_motor.set(duty_right)

    def _apply_deadband(self, duty: float) -> float:
        db = self.g['min_pwm_duty']
        if abs(duty) < 1e-3:
            return 0.0
        # Scale so that a tiny commanded duty becomes at least db.
        sign = 1.0 if duty > 0 else -1.0
        mag = min(1.0, db + (1.0 - db) * abs(duty))
        return sign * mag

    # ---------- odometry loop -------------------------------------------
    def odom_step(self) -> None:
        # Consume ticks accumulated since last call.
        d_ticks_left  = self.left_enc.read_and_reset()
        d_ticks_right = self.right_enc.read_and_reset()
        self._left_ticks_total  += d_ticks_left
        self._right_ticks_total += d_ticks_right

        # ticks → wheel distance (metres).
        ticks_per_rev = self.g['encoder_ticks_per_revolution']
        circumference = 2.0 * math.pi * self.g['wheel_radius']
        d_left  = (d_ticks_left  / ticks_per_rev) * circumference
        d_right = (d_ticks_right / ticks_per_rev) * circumference

        # Update pose (standard diff-drive integration).
        d_center = 0.5 * (d_left + d_right)
        d_yaw    = (d_right - d_left) / self.g['wheel_separation']

        now = self.get_clock().now()
        dt = (now - self.last_odom_time).nanoseconds * 1e-9
        self.last_odom_time = now
        dt = max(1e-6, dt)

        self.odom.yaw += d_yaw
        # Normalize yaw to [-pi, pi].
        self.odom.yaw = math.atan2(math.sin(self.odom.yaw), math.cos(self.odom.yaw))
        self.odom.x += d_center * math.cos(self.odom.yaw)
        self.odom.y += d_center * math.sin(self.odom.yaw)
        self.odom.vx = d_center / dt
        self.odom.wz = d_yaw    / dt

        self._publish_odom(now)
        self._publish_ticks()

    def _publish_odom(self, stamp: Time) -> None:
        msg = Odometry()
        msg.header.stamp = stamp.to_msg()
        msg.header.frame_id = self.g['odom_frame']
        msg.child_frame_id = self.g['base_frame']
        msg.pose.pose.position.x = self.odom.x
        msg.pose.pose.position.y = self.odom.y
        msg.pose.pose.orientation = yaw_to_quat(self.odom.yaw)
        msg.twist.twist.linear.x = self.odom.vx
        msg.twist.twist.angular.z = self.odom.wz
        # Rough covariances - tune per your encoder resolution.
        msg.pose.covariance[0]  = 0.01
        msg.pose.covariance[7]  = 0.01
        msg.pose.covariance[35] = 0.05
        msg.twist.covariance[0]  = 0.01
        msg.twist.covariance[35] = 0.05
        self.odom_pub.publish(msg)

        if self.g['publish_odom_tf']:
            t = TransformStamped()
            t.header.stamp = stamp.to_msg()
            t.header.frame_id = self.g['odom_frame']
            t.child_frame_id = self.g['base_frame']
            t.transform.translation.x = self.odom.x
            t.transform.translation.y = self.odom.y
            t.transform.rotation = yaw_to_quat(self.odom.yaw)
            self.tf_broadcaster.sendTransform(t)

    def _publish_ticks(self) -> None:
        msg = Int32MultiArray()
        msg.data = [self._left_ticks_total, self._right_ticks_total]
        self.ticks_pub.publish(msg)

    # ---------- shutdown -------------------------------------------------
    def destroy_node(self):
        try:
            self.left_motor.stop()
            self.right_motor.stop()
        finally:
            super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MibotDriveNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
