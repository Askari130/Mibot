"""Full Mibot bring-up: everything the robot needs to run.

Started on the Pi with:
  ros2 launch mibot_bringup mibot.launch.py

Launch arguments (all optional):
  serial_port:=/dev/ttyUSB0     # override RPLIDAR device name
  include_rplidar:=true
  include_camera:=true
  include_teleop:=true          # twist_mux
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    description_share = FindPackageShare('mibot_description')
    drive_share       = FindPackageShare('mibot_drive')
    teleop_share      = FindPackageShare('mibot_teleop')

    serial_port      = LaunchConfiguration('serial_port')
    include_rplidar  = LaunchConfiguration('include_rplidar')
    include_camera   = LaunchConfiguration('include_camera')
    include_teleop   = LaunchConfiguration('include_teleop')

    hardware_yaml = PathJoinSubstitution([drive_share, 'config', 'hardware.yaml'])
    twist_mux_yaml = PathJoinSubstitution([teleop_share, 'config', 'twist_mux.yaml'])

    # --- robot_state_publisher -----------------------------------------
    rsp_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([description_share, 'launch', 'rsp.launch.py'])
        )
    )

    # --- motor driver + odometry ---------------------------------------
    drive_node = Node(
        package='mibot_drive',
        executable='drive_node',
        name='mibot_drive',
        output='screen',
        parameters=[hardware_yaml],
    )

    # --- twist_mux (teleop + Nav2 arbitration) -------------------------
    twist_mux_node = Node(
        package='twist_mux',
        executable='twist_mux',
        name='twist_mux',
        output='screen',
        parameters=[twist_mux_yaml],
        remappings=[('/cmd_vel_out', '/cmd_vel')],
        condition=IfCondition(include_teleop),
    )

    # --- RPLIDAR -------------------------------------------------------
    rplidar_node = Node(
        package='rplidar_ros',
        executable='rplidar_composition',
        name='rplidar_node',
        output='screen',
        parameters=[{
            'serial_port':       serial_port,
            'serial_baudrate':   115200,   # A1 = 115200, A2M8 = 256000
            'frame_id':          'lidar_link',
            'inverted':          False,
            'angle_compensate':  True,
        }],
        condition=IfCondition(include_rplidar),
    )

    # --- Camera (USB webcam via v4l2_camera) ---------------------------
    camera_node = Node(
        package='v4l2_camera',
        executable='v4l2_camera_node',
        name='camera_node',
        output='screen',
        parameters=[{
            'video_device': '/dev/video0',
            'image_size':   [640, 480],
            'camera_frame_id': 'camera_link_optical',
        }],
        condition=IfCondition(include_camera),
    )

    return LaunchDescription([
        DeclareLaunchArgument('serial_port',     default_value='/dev/ttyUSB_LIDAR'),
        DeclareLaunchArgument('include_rplidar', default_value='true'),
        DeclareLaunchArgument('include_camera',  default_value='true'),
        DeclareLaunchArgument('include_teleop',  default_value='true'),

        rsp_launch,
        drive_node,
        twist_mux_node,
        rplidar_node,
        camera_node,
    ])
