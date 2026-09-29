"""Launch robot_state_publisher with the Mibot URDF.

Usage:
  ros2 launch mibot_description rsp.launch.py
  ros2 launch mibot_description rsp.launch.py use_sim_time:=true
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    pkg_share = FindPackageShare('mibot_description')

    use_sim_time = LaunchConfiguration('use_sim_time')

    # xacro is run at launch time so parameter changes in the .xacro file
    # take effect on the next `ros2 launch`, no `colcon build` needed.
    xacro_file = PathJoinSubstitution([pkg_share, 'urdf', 'mibot.urdf.xacro'])
    robot_description = Command(['xacro ', xacro_file])

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use simulation clock (set true when running under Gazebo).',
        ),

        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{
                'robot_description': robot_description,
                'use_sim_time': use_sim_time,
            }],
        ),
    ])
