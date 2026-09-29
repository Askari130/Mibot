"""Run teleop_twist_keyboard, remapped onto Mibot's twist_mux input.

  ros2 launch mibot_teleop keyboard_teleop.launch.py

Keys (standard teleop_twist_keyboard layout):
   u  i  o
   j  k  l          i = forward, k = stop, , = reverse
   m  ,  .          j / l = turn

The keyboard node publishes to /cmd_vel_key rather than /cmd_vel so that
twist_mux (started by mibot_bringup) can arbitrate against Nav2 and joy.
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        Node(
            package='teleop_twist_keyboard',
            executable='teleop_twist_keyboard',
            name='teleop_twist_keyboard',
            output='screen',
            prefix='xterm -e',
            remappings=[('/cmd_vel', '/cmd_vel_key')],
        ),
    ])
