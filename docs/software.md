# Software

Mibot runs a stock ROS 2 stack. This file covers the OS, packages, workspace layout, and every command to get from a fresh Raspberry Pi to a working SLAM demo.

![RViz2 showing the SLAM map and LaserScan overlay](images/rviz-slam-map.png)
> *SLAM map produced by driving Mibot around a room, viewed in RViz2 with `Fixed Frame = map`, plus `RobotModel`, `LaserScan`, `Camera`, and `Map` displays.*

## Stack

| Layer | Choice |
|---|---|
| OS | Ubuntu 22.04 Server (64-bit) on the Raspberry Pi 4 |
| Middleware | ROS 2 Humble Hawksbill |
| Robot description | URDF/Xacro |
| Simulation | Gazebo (optional, for testing before the real robot exists) |
| Motor control | `ros2_control` with `diff_drive_controller` and a small `hardware_interface` that drives the L298N over GPIO and reads the rear-wheel quadrature encoders (one per side) |
| LIDAR driver | Whichever driver package matches your LIDAR (`rplidar_ros`, `ldlidar_stl_ros2`, `sllidar_ros2`, …) |
| Camera driver | `v4l2_camera` (USB webcam) or `camera_ros` (Pi Camera via libcamera) |
| Teleop | `teleop_twist_keyboard`, `teleop_twist_joy` |
| Twist arbitration | `twist_mux` |
| SLAM | `slam_toolbox` (async online mode) |
| Navigation | `nav2_bringup` — planned, not yet running end-to-end |
| Visualisation | RViz2 |

## Prerequisites

On the Raspberry Pi:

1. **Ubuntu 22.04 Server 64-bit** flashed to the microSD card (Raspberry Pi Imager → *Other general-purpose OS* → Ubuntu).
2. **Set the hostname to `mibot`** and enable SSH during imaging so you can work from your laptop.
3. **ROS 2 Humble** — follow the [official install guide for Ubuntu 22.04](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debians.html). Install `ros-humble-ros-base` (not desktop — the Pi doesn't need RViz).
4. Add your user to the `dialup`/`dialout` and `gpio` groups so you can access GPIO and USB without `sudo`:

   ```bash
   sudo usermod -aG dialout,gpio $USER
   ```

On your laptop (for driving/visualisation):

1. Ubuntu 22.04 + ROS 2 Humble **desktop** (`ros-humble-desktop`).
2. Same ROS domain ID as the Pi (see below).

## Workspace layout

```
~/mibot_ws/
└── src/
    ├── mibot_description/     # URDF/Xacro, meshes, RViz configs
    ├── mibot_bringup/         # launch files that start the whole robot
    ├── mibot_hardware/        # hardware_interface for the L298N via GPIO
    ├── mibot_teleop/          # twist_mux + teleop launch
    └── mibot_slam/            # slam_toolbox params + launch
```

Each package is a standard `ament_cmake` (C++) or `ament_python` (Python) package. `mibot_bringup` is the one you launch — everything else is a dependency.

## Install

```bash
# 1. Clone this repo into your ROS 2 workspace
mkdir -p ~/mibot_ws/src
cd ~/mibot_ws/src
git clone https://github.com/Askari130/Mibot.git

# 2. Install ROS 2 dependencies
cd ~/mibot_ws
sudo apt update
sudo rosdep init      # first time only, ignore if it says already initialised
rosdep update
rosdep install --from-paths src --ignore-src -r -y

# 3. Extra apt packages Mibot uses directly
sudo apt install -y \
    ros-humble-ros2-control \
    ros-humble-ros2-controllers \
    ros-humble-slam-toolbox \
    ros-humble-nav2-bringup \
    ros-humble-twist-mux \
    ros-humble-teleop-twist-keyboard \
    ros-humble-teleop-twist-joy \
    ros-humble-v4l2-camera \
    ros-humble-image-transport-plugins

# 4. Build
colcon build --symlink-install
source install/setup.bash
```

## Configuration

### ROS domain ID

Set the same domain ID on the Pi and on your laptop, in `~/.bashrc`:

```bash
export ROS_DOMAIN_ID=42
```

Any number 0–101 works; picking one keeps you off other people's robots on the same Wi-Fi.

### LIDAR device name

The LIDAR shows up as `/dev/ttyUSB0` by default, but that name changes if you plug things in a different order. Give it a stable name with a udev rule — `lsusb` gets the vendor and product IDs, then:

```bash
# /etc/udev/rules.d/99-mibot-lidar.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="mibot_lidar", MODE="0666"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Then point the LIDAR launch file at `/dev/mibot_lidar`.

### URDF measurements

Update these in `mibot_description/urdf/mibot.urdf.xacro` to match your actual chassis:

- `wheel_radius`
- `wheel_separation` (centre-to-centre between the left and right sides)
- `base_link → lidar_link` translation (LIDAR mount height above the chassis, forward offset)
- `base_link → camera_link` translation

Get these wrong and SLAM will drift or the map will look scaled oddly.

### Encoder config

Only the two rear motors are encoded. `mibot_hardware` reads one encoder per side and reports that as the wheel state to `diff_drive_controller`. In `mibot_hardware/config/hardware.yaml`:

```yaml
mibot_hardware:
  ros__parameters:
    # L298N control pins (BCM numbering)
    left_pwm_pin: 12
    left_dir_a_pin: 23
    left_dir_b_pin: 24
    right_pwm_pin: 13
    right_dir_a_pin: 27
    right_dir_b_pin: 22

    # Rear-motor quadrature encoders (BCM numbering)
    left_encoder_a_pin: 5
    left_encoder_b_pin: 6
    right_encoder_a_pin: 16
    right_encoder_b_pin: 26

    # Measure this yourself: roll the wheel by hand one turn, count raw ticks
    encoder_ticks_per_revolution: 40
    invert_left_encoder: false
    invert_right_encoder: false
```

**How to measure `encoder_ticks_per_revolution`:**

```bash
# On the Pi, in one terminal
ros2 launch mibot_bringup mibot.launch.py

# In another
ros2 topic echo /wheel_ticks
```

Lift the wheel, mark the tyre with a piece of tape, and roll it exactly one full revolution by hand. The difference between the tick counter before and after is your value. Do it three times and average; put the number in `hardware.yaml`.

If odometry drifts forwards or backwards when the robot spins in place, flip `invert_left_encoder` or `invert_right_encoder`. If odometry reads a *distance* that's consistently, say, 10% short over a measured 1 m push, your ticks-per-rev value or `wheel_radius` is off by that ratio.

## Running Mibot

### 1. Bring up the robot (on the Pi)

```bash
ssh mibot@mibot.local
cd ~/mibot_ws && source install/setup.bash
ros2 launch mibot_bringup mibot.launch.py
```

This starts:

- `robot_state_publisher` (URDF → TF tree)
- `controller_manager` + `diff_drive_controller` + the L298N hardware interface
- LIDAR driver
- Camera driver
- `twist_mux` (so teleop and Nav2 can share `/cmd_vel` without fighting)

### 2. Teleoperate (on your laptop)

Keyboard:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard \
    --ros-args -r cmd_vel:=/cmd_vel_key
```

`cmd_vel_key` is one of `twist_mux`'s inputs, so it gets routed through to the controller with a priority lower than Nav2 but higher than "nothing".

Gamepad:

```bash
ros2 launch mibot_teleop joy_teleop.launch.py
```

### 3. SLAM (on the Pi, or on your laptop if the Wi-Fi is good enough)

```bash
ros2 launch slam_toolbox online_async_launch.py \
    slam_params_file:=$(ros2 pkg prefix mibot_slam)/share/mibot_slam/config/mapper_params_online_async.yaml
```

Drive Mibot around the room. When the map looks good in RViz, save it:

```bash
ros2 run nav2_map_server map_saver_cli -f ~/mibot_ws/maps/my_room
```

### 4. Visualise (on your laptop)

```bash
ros2 run rviz2 rviz2 -d ~/mibot_ws/src/Mibot/config/mibot.rviz
```

Displays configured in the RViz file, matching the screenshot above:

- **Fixed Frame:** `map`
- **RobotModel** on `/robot_description`
- **LaserScan** on `/scan`
- **Camera** on `/image_raw`
- **Map** on `/map`
- **TF** and **Grid** for reference

### 5. Navigation (planned)

Once mapping is stable:

```bash
ros2 launch nav2_bringup bringup_launch.py \
    map:=~/mibot_ws/maps/my_room.yaml \
    use_sim_time:=false
```

Then set a `2D Pose Estimate` and `2D Goal Pose` in RViz.

## Topics you'll actually use

| Topic | Type | Notes |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | Output of `twist_mux` → into `diff_drive_controller` |
| `/cmd_vel_key` | `geometry_msgs/Twist` | Keyboard teleop input |
| `/cmd_vel_joy` | `geometry_msgs/Twist` | Gamepad teleop input |
| `/cmd_vel_nav` | `geometry_msgs/Twist` | Nav2 output |
| `/scan` | `sensor_msgs/LaserScan` | LIDAR |
| `/image_raw` | `sensor_msgs/Image` | Camera |
| `/odom` | `nav_msgs/Odometry` | From `diff_drive_controller`, computed from the rear quadrature encoders — closed-loop |
| `/wheel_ticks` | `mibot_msgs/WheelTicks` | Raw encoder tick counts (for tuning and debugging) |
| `/tf`, `/tf_static` | `tf2_msgs/TFMessage` | Transforms |
| `/map` | `nav_msgs/OccupancyGrid` | SLAM output |

## Troubleshooting

- **Motors twitch but don't spin** — L298N enable pins (`ENA`/`ENB`) probably aren't getting PWM. Check the GPIO pins in `mibot_hardware` config match the wiring in [`hardware.md`](hardware.md).
- **One side drives backwards** — flip the two motor wires at the L298N for that side. Faster than fixing in code, and it removes a permanent sign-flip you'd otherwise have to remember.
- **LIDAR shows up but SLAM stays blank** — TF is probably wrong. Run `ros2 run tf2_tools view_frames` and confirm `map → odom → base_link → lidar_link` all exist.
- **RViz shows the LIDAR scan but no robot model** — `Fixed Frame` is set to something that doesn't exist yet. Start with `Fixed Frame = base_link` while there's no map, then switch to `map` after SLAM starts publishing.
- **Camera drops frames over Wi-Fi** — use `image_transport` with `compressed` on the laptop side: subscribe to `/image_raw/compressed` in RViz instead of `/image_raw`.
- **Odometry drifts backwards when robot goes forward** — an encoder channel is inverted. Flip `invert_left_encoder` or `invert_right_encoder` in `hardware.yaml`, whichever side is wrong.
- **Encoder ticks stay at zero** — either `VCC` isn't reaching the encoder board (check with a multimeter, some modules want 5 V not 3.3 V), or the A/B channels are wired to non-interrupt pins. GPIO 5, 6, 16, 26 all work; other pins may miss ticks at speed.
- **Robot drives straight but odometry says it's turning** — one side's wheel radius is off, or one encoder is missing every other tick. Compare `/wheel_ticks` from the left and right over a straight 1 m push; they should be within a few percent.

## References

- [Articulated Robotics — Building a Mobile Robot playlist](https://youtube.com/playlist?list=PLunhqkrRNRhYAffV8JDiFOatQXuU-NnxT) — the tutorial series this build follows.
- [ROS 2 Humble docs](https://docs.ros.org/en/humble/)
- [`slam_toolbox`](https://github.com/SteveMacenski/slam_toolbox)
- [Nav2](https://docs.nav2.org/)
- [`ros2_control` docs](https://control.ros.org/humble/index.html)
