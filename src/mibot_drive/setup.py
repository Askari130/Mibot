from setuptools import find_packages, setup
from glob import glob

package_name = 'mibot_drive'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Muqaddis Adedeji Olopade',
    maintainer_email='muqaddiso@gmail.com',
    description='Mibot cmd_vel -> GPIO differential drive with encoder odometry.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'drive_node = mibot_drive.drive_node:main',
        ],
    },
)
