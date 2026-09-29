"""Gamepad teleop for Mibot via teleop_twist_joy → /cmd_vel_joy.

  ros2 launch mibot_teleop joy_teleop.launch.py

Defaults assume an Xbox-style controller: left stick for translation,
right stick for rotation. Left bumper is the enable-turbo button.
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        Node(
            package='joy',
            executable='joy_node',
            name='joy_node',
            output='screen',
            parameters=[{
                'device_id': 0,
                'deadzone': 0.05,
                'autorepeat_rate': 20.0,
            }],
        ),

        Node(
            package='teleop_twist_joy',
            executable='teleop_node',
            name='teleop_twist_joy',
            output='screen',
            parameters=[{
                'require_enable_button': True,
                'enable_button':          4,     # LB
                'enable_turbo_button':    5,     # RB
                'axis_linear.x':          1,     # left stick vertical
                'axis_angular.yaw':       3,     # right stick horizontal
                'scale_linear.x':         0.3,
                'scale_angular.yaw':      1.0,
                'scale_linear_turbo.x':   0.6,
                'scale_angular_turbo.yaw': 2.0,
            }],
            remappings=[('/cmd_vel', '/cmd_vel_joy')],
        ),
    ])
