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
| Motor control | `mibot_drive` — a plain Python `rclpy` node that subscribes to `/cmd_vel`, drives the L298N via GPIO PWM (`gpiozero`), reads the rear-wheel quadrature encoders, and publishes `/odom` + TF. `ros2_control` migration is future work. |
| LIDAR driver | `rplidar_ros` (or `sllidar_ros2`) for the Slamtec RPLIDAR |
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
└── src/                        (= this repo's src/)
    ├── mibot_description/      # URDF/Xacro, RViz config, robot_state_publisher launch
    ├── mibot_drive/            # cmd_vel -> L298N GPIO + encoder odometry (Python)
    ├── mibot_bringup/          # top-level launch: rsp + drive + rplidar + camera + twist_mux
    ├── mibot_teleop/           # twist_mux config + keyboard/joystick teleop launch
    └── mibot_slam/             # slam_toolbox params + launch
```

`mibot_description` is `ament_cmake`; the other four are `ament_python`. `mibot_bringup` is the one you launch — everything else is a dependency.

## Install

```bash
# 1. Clone this repo. The ROS 2 packages live under its src/ folder,
#    so treat the whole repo as your workspace.
git clone https://github.com/Askari130/Mibot.git ~/mibot_ws
cd ~/mibot_ws

# 2. Install ROS 2 dependencies
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
    ros-humble-image-transport-plugins \
    ros-humble-rplidar-ros \
    ros-humble-xacro

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

The RPLIDAR shows up as `/dev/ttyUSB0` by default, but that name changes if you plug things in a different order. Give it a stable name with a udev rule — the Slamtec CP210x adapter's IDs (`10c4:ea60`) are the common ones, but confirm with `lsusb`:

```bash
# /etc/udev/rules.d/99-mibot-lidar.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="ttyUSB_LIDAR", MODE="0666"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Then point the LIDAR launch file at `/dev/ttyUSB_LIDAR`.

If the udev rule doesn't take (LIDAR-driver launches fail with "no such device"), fall back to whatever it actually enumerated as:

```bash
ls /dev/ttyUSB*
# then override the launch arg
ros2 launch mibot_bringup mibot.launch.py serial_port:=/dev/ttyUSB0
```

### URDF measurements

Update these in `mibot_description/urdf/mibot.urdf.xacro` to match your actual chassis:

- `wheel_radius`
- `wheel_separation` (centre-to-centre between the left and right sides)
- `base_link → lidar_link` translation (LIDAR mount height above the chassis, forward offset)
- `base_link → camera_link` translation

Get these wrong and SLAM will drift or the map will look scaled oddly.

### Encoder config

Only the two rear motors are encoded. `mibot_drive` reads one encoder per side and integrates them into `/odom`. In `mibot_drive/config/hardware.yaml`:

```yaml
mibot_drive:
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

The full parameter list — including geometry (`wheel_radius`, `wheel_separation`), motor calibration (`max_linear_speed`, `min_pwm_duty`), loop rates, and TF/frame settings — is in [`src/mibot_drive/config/hardware.yaml`](../src/mibot_drive/config/hardware.yaml).

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
| `/wheel_ticks` | `std_msgs/Int32MultiArray` | `[left_total, right_total]` raw encoder tick counts (for tuning and debugging) |
| `/tf`, `/tf_static` | `tf2_msgs/TFMessage` | Transforms |
| `/map` | `nav_msgs/OccupancyGrid` | SLAM output |

## Simulation (Gazebo)

Before running on the real robot, the URDF and the differential-drive controller are worth verifying in Gazebo. The same `mibot_description` package feeds both.

```bash
ros2 launch mibot_description gazebo.launch.py
```

Then teleop the simulated robot with the same `teleop_twist_keyboard` command as the real one.

**Note on GPU:** if you're developing on an older laptop (the reference dev machine is a Dell Precision M4800 with a Quadro K1100M), turn down Gazebo's shadow and reflection settings, or use `gz sim --render-engine ogre` instead of `ogre2`, otherwise the sim slows to a crawl and physics can go non-real-time.

### Fixing the Gazebo GPG key on a fresh Ubuntu 22.04 install

The OSRF signing key has been rotated. If `apt update` complains about `EXPKEYSIG F42ED6FBAB17C654 Open Robotics`, do this instead of using the deprecated `apt-key`:

```bash
# 1. Remove the old expired key if it's there
sudo apt-key del F42ED6FBAB17C654 2>/dev/null || true

# 2. Install the new key into a dedicated keyring
curl -fsSL https://packages.osrfoundation.org/gazebo.key \
  | gpg --dearmor \
  | sudo tee /usr/share/keyrings/gazebo-archive-keyring.gpg > /dev/null

# 3. Re-add the source list, signed by that keyring
echo "deb [signed-by=/usr/share/keyrings/gazebo-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null

# 4. Update and install
sudo apt update
sudo apt install -y gazebo libgazebo-dev
```

## Troubleshooting

### Robot / motors

- **Motors twitch but don't spin** — L298N enable pins (`ENA`/`ENB`) probably aren't getting PWM. Check the GPIO pins in `mibot_drive/config/hardware.yaml` match the wiring in [`hardware.md`](hardware.md).
- **One side drives backwards** — flip the two motor wires at the L298N for that side. Faster than fixing in code, and it removes a permanent sign-flip you'd otherwise have to remember.

### Controllers (`ros2 control`)

- **`ros2 control list_controllers` shows the controller as `unconfigured` or missing entirely** — the spawner didn't come up. Confirm `controller_manager` is running (`ros2 node list | grep controller_manager`), then check its config YAML is being loaded by the launch file. A healthy state looks like:

  ```
  robot_base_controller  diff_drive_controller/DiffDriveController  active
  joint_state_broadcaster  joint_state_broadcaster/JointStateBroadcaster  active
  ```

- **Publishing to `/cmd_vel` does nothing but the controller says `active`** — check the actual topic the controller subscribes to. Some setups use `/robot_base_controller/cmd_vel_unstamped`. Verify:

  ```bash
  ros2 topic info /robot_base_controller/cmd_vel_unstamped
  # Subscriber count should be 1
  ```

  If subscriber count is 0, the controller isn't wired up correctly.

### Launch / URDF

- **`ros2 param get /robot_state_publisher robot_description` → "Node not found"** — the `robot_state_publisher` either crashed or hasn't finished starting yet. Two fixes:
  1. Confirm the launch file actually processes the xacro and passes it to `robot_state_publisher`:

     ```python
     from ament_index_python.packages import get_package_share_directory
     import xacro

     robot_description_config = xacro.process_file(
         os.path.join(
             get_package_share_directory('mibot_description'),
             'urdf', 'mibot.urdf.xacro'
         )
     )

     robot_state_publisher = Node(
         package='robot_state_publisher',
         executable='robot_state_publisher',
         parameters=[{'robot_description': robot_description_config.toxml()}],
     )
     ```

  2. If a downstream node reads `robot_description` too early (race condition), wrap that read in a `TimerAction` to give `robot_state_publisher` time to register:

     ```python
     from launch.actions import TimerAction

     TimerAction(period=2.0, actions=[
         ExecuteProcess(cmd=[
             "ros2", "param", "get", "--hide-type",
             "/robot_state_publisher", "robot_description"
         ])
     ])
     ```

### LIDAR / SLAM

- **LIDAR shows up but SLAM stays blank** — TF is probably wrong. Run `ros2 run tf2_tools view_frames` and confirm `map → odom → base_link → lidar_link` all exist.
- **RViz shows the LIDAR scan but no robot model** — `Fixed Frame` is set to something that doesn't exist yet. Start with `Fixed Frame = base_link` while there's no map, then switch to `map` after SLAM starts publishing.
- **LIDAR driver fails with "no such device"** — the port isn't `/dev/ttyUSB_LIDAR` (or whatever the udev rule sets). List real ones and override:

  ```bash
  ls /dev/ttyUSB*
  ros2 launch mibot_bringup mibot.launch.py serial_port:=/dev/ttyUSB0
  ```

### Camera

- **Camera drops frames over Wi-Fi** — use `image_transport` with `compressed` on the laptop side: subscribe to `/image_raw/compressed` in RViz instead of `/image_raw`.

### Odometry / encoders

- **Odometry drifts backwards when robot goes forward** — an encoder channel is inverted. Flip `invert_left_encoder` or `invert_right_encoder` in `hardware.yaml`, whichever side is wrong.
- **Encoder ticks stay at zero** — either `VCC` isn't reaching the encoder board (check with a multimeter, some modules want 5 V not 3.3 V), or the A/B channels are wired to non-interrupt pins. GPIO 5, 6, 16, 26 all work; other pins may miss ticks at speed.
- **Robot drives straight but odometry says it's turning** — one side's wheel radius is off, or one encoder is missing every other tick. Compare `/wheel_ticks` from the left and right over a straight 1 m push; they should be within a few percent.

### Teleop

- **`teleop_twist_keyboard` runs but nothing moves** — the key layout is `u i o / j k l / m , .`. `i` = forward, `,` = reverse, `j` / `l` = turn, `k` = stop. If the terminal loses focus, keys don't register. Also verify remapping: the node publishes to `/cmd_vel` by default, but Mibot's `twist_mux` expects `/cmd_vel_key`:

  ```bash
  ros2 run teleop_twist_keyboard teleop_twist_keyboard \
      --ros-args -r cmd_vel:=/cmd_vel_key
  ```

## References

- [Articulated Robotics — Building a Mobile Robot playlist](https://youtube.com/playlist?list=PLunhqkrRNRhYAffV8JDiFOatQXuU-NnxT) — the tutorial series this build follows.
- [Andino](https://github.com/Ekumen-OS/andino) — Ekumen's open-source ROS 2 differential-drive robot. The `andino_bringup` launch structure (e.g. `include_rplidar:=True include_camera:=True serial_port:=/dev/ttyUSB0`) is the pattern Mibot's own bring-up borrows from.
- [PARC 2025 Autonomy Track docs](https://parc-robotics.github.io/documentation-2025/competition-instructions/phase-1/autonomy-track/) — earlier work on maze navigation in Gazebo that this repo grew out of.
- [ROS 2 Humble docs](https://docs.ros.org/en/humble/)
- [`slam_toolbox`](https://github.com/SteveMacenski/slam_toolbox)
- [Nav2](https://docs.nav2.org/)
- [`ros2_control` docs](https://control.ros.org/humble/index.html)
- [`rplidar_ros`](https://github.com/Slamtec/rplidar_ros) / [`sllidar_ros2`](https://github.com/Slamtec/sllidar_ros2) — Slamtec's official RPLIDAR drivers.
