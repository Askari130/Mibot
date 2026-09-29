"""Start slam_toolbox in async online mapping mode.

  ros2 launch mibot_slam slam.launch.py

Drive Mibot around the room; the map builds live. When it looks good:
  ros2 run nav2_map_server map_saver_cli -f ~/mibot_ws/maps/my_room
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    slam_share = FindPackageShare('mibot_slam')
    params = PathJoinSubstitution([slam_share, 'config', 'mapper_params_online_async.yaml'])
    use_sim_time = LaunchConfiguration('use_sim_time')

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='false'),

        Node(
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[params, {'use_sim_time': use_sim_time}],
        ),
    ])
