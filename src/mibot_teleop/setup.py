from setuptools import find_packages, setup
from glob import glob

package_name = 'mibot_teleop'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Muqaddis Adedeji Olopade',
    maintainer_email='muqaddiso@gmail.com',
    description='Mibot teleop and twist_mux configs.',
    license='MIT',
    entry_points={'console_scripts': []},
)
