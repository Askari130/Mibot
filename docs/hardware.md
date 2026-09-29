# Hardware

This is the physical build of Mibot — what parts I used, how they're wired together, and the notes I wish I had when I was assembling it.

![Mibot with Pi 4, L298N, and Energizer power bank](images/mibot-chassis.jpg)

## Bill of materials

Everything visible in the photo, plus the bits mounted underneath or hidden by wiring.

### Chassis and drivetrain

| Item | Notes |
|---|---|
| 4-wheel plastic "smart car" chassis (blue) | Two-deck design — motors and battery holder on the lower deck, electronics on the upper deck. |
| 2 × DC gear motors, yellow "TT" style (front) | Front-left and front-right. No encoders — they just spin. Wired in parallel with the rear motor on the same side. |
| 2 × DC gear motors **with quadrature encoders** (rear) | Rear-left and rear-right. Same physical size as the TT motors so they drop into the chassis, but with a Hall-effect encoder on the back of each. These are what feeds real odometry back to ROS 2. |
| 4 × wheels | Come with the chassis. |
| M3 standoffs and screws | For mounting the Pi, motor driver, and battery holder. |

> **Why only two encoders?** `diff_drive_controller` needs one encoder per side, not per wheel. As long as each side's front and rear motors are wired in parallel (so they spin together), one encoded rear motor per side gives the controller everything it needs.

### Compute and electronics

| Item | Notes |
|---|---|
| Raspberry Pi 4 Model B (4 GB) | In the red case at the front-left of the chassis. Runs Ubuntu 22.04 Server + ROS 2 Humble. |
| L298N dual H-bridge motor driver | The red board mounted centrally. Two channels — one drives the left pair, one the right. |
| Jumper wires (male-to-female, red/yellow/black) | For GPIO ↔ L298N control lines and power. |
| microSD card, 32 GB Class 10 | Boot media for the Pi. |

### Sensors

| Item | Notes |
|---|---|
| 2D LIDAR | Used for SLAM and visualised as `LaserScan` in RViz2. Common cheap options that work with the same driver: RPLIDAR A1 / LD06 / LD19 — set the model you actually bought here. |
| Camera | Mounted on top when running. Either a Pi Camera Module (via CSI ribbon) or a USB webcam — set which one you're using in [`software.md`](software.md). |

### Power

| Item | Notes |
|---|---|
| Energizer USB power bank | The black block sitting on the chassis. Powers the Raspberry Pi over USB-C. |
| Battery pack for motors | Separate from the Pi's power bank — an L298N needs a dedicated motor supply so brown-outs from stall current don't reset the Pi. A 4×AA holder (6 V) or a 2S/3S Li-ion pack both work, up to ~12 V. |
| Toggle / rocker switch | Optional, wired between motor battery and L298N `VCC` so you can kill drive without unplugging the Pi. |

## Wiring

### L298N ↔ Raspberry Pi (GPIO)

The L298N takes two direction pins and one PWM (enable) pin per motor. Wired as a two-side differential drive:

| L298N pin | Raspberry Pi (BCM) | Purpose |
|---|---|---|
| `ENA` | GPIO 12 (PWM0) | Left side speed |
| `IN1` | GPIO 23 | Left side direction A |
| `IN2` | GPIO 24 | Left side direction B |
| `ENB` | GPIO 13 (PWM1) | Right side speed |
| `IN3` | GPIO 27 | Right side direction A |
| `IN4` | GPIO 22 | Right side direction B |
| `GND` | GND (pin 6, 9, 14, …) | Common ground with the Pi — **required**, or the direction pins float. |

> The GPIO numbers above match my `mibot_bringup` config. Change them there and here together if you re-pin.

### L298N ↔ Motors

| L298N pin | Motor |
|---|---|
| `OUT1` / `OUT2` | Left side — front-left (TT) and rear-left (encoded) wired in parallel, same polarity |
| `OUT3` / `OUT4` | Right side — front-right (TT) and rear-right (encoded) wired in parallel, same polarity |

If one side spins backwards when the other spins forwards on the same command, swap that side's two wires at the L298N — cheaper than fixing it in code.

> **Wiring the front + rear motors in parallel:** the two motor terminals on each side both go to the same L298N output pair. Match the polarity (both motors' `+` terminal to the same `OUT`), otherwise the front and rear on that side will fight each other.

### Encoders ↔ Raspberry Pi (GPIO)

Each encoded rear motor has a small PCB on the back with 6 leads: motor power (2), encoder power (2), and two quadrature channels (`A` and `B`). Motor power is already handled above via the L298N. What's left is the encoder side:

| Encoder pin | Raspberry Pi (BCM) | Purpose |
|---|---|---|
| Left rear `VCC` | 3.3 V (pin 1) | Encoder logic supply — check your encoder module's spec, some want 5 V |
| Left rear `GND` | GND | Common ground |
| Left rear `A` | GPIO 5 | Left wheel quadrature channel A |
| Left rear `B` | GPIO 6 | Left wheel quadrature channel B |
| Right rear `VCC` | 3.3 V (pin 17) | Encoder logic supply |
| Right rear `GND` | GND | Common ground |
| Right rear `A` | GPIO 16 | Right wheel quadrature channel A |
| Right rear `B` | GPIO 26 | Right wheel quadrature channel B |

The four encoder-channel pins (5, 6, 16, 26) are all interrupt-capable on the Pi 4 and none of them clash with the L298N pins or the LIDAR/camera USB — so this pinout can go straight in.

> **Ticks per revolution:** measure it. Roll the wheel by hand one full turn while `mibot_hardware` logs raw ticks and note the number — that's what goes into `encoder_ticks_per_revolution` in the ROS 2 config. Common values are 20, 40, or 11 × the internal gear ratio; the actual number depends on your specific encoder module.

### Power

- **Pi:** USB-C from the Energizer power bank. Keep it topped up; ROS 2 + Wi-Fi + camera streaming will pull ~2 A.
- **L298N `+12V` (motor rail):** motor battery pack positive. Do **not** power motors from the Pi's 5 V rail — the L298N will happily brown the Pi out.
- **L298N `+5V`:** leave the on-board 5 V regulator jumper enabled and feed the logic side from the motor rail, *or* jumper `+5V` from the Pi's 5 V pin. Pick one — don't do both.
- **Common ground:** L298N `GND` → Pi `GND` → motor-battery `-`. All three must be tied together.

### Sensors

- **LIDAR:** USB into the Pi. Most cheap 2D LIDARs enumerate as `/dev/ttyUSB0`; udev rules to give it a stable name are in [`software.md`](software.md).
- **Camera:** either the CSI ribbon into the Pi's camera connector (Pi Camera) or USB (webcam).

## Physical assembly notes

1. **Build the lower deck first** — motors screwed into the chassis, wired to L298N with the battery holder tucked in beside them. Confirm each motor spins the right way with a bench supply before mounting the top deck; it's a lot of screws to undo later.
2. **Mount the L298N in the middle** so the four motor leads reach without extensions and heat can escape from the heatsink.
3. **Put the Pi at one end and the power bank at the opposite end** for balance. Mine has the Pi at the front and the power bank across the middle-rear.
4. **Route the motor wires under the top deck**, and the Pi ↔ L298N jumpers over the top. Keeps high-current noisy wiring away from GPIO signal lines.
5. **LIDAR goes on the very top**, centered, facing forward, with an unobstructed 360° view. Any part of the robot that sits above the LIDAR plane will show up in every map as a fake obstacle.
6. **Camera goes at the front, above the LIDAR** if you can — otherwise the LIDAR sees the back of the camera mount as a permanent blocker in front of the robot.
7. Measure `wheel_radius`, `wheel_separation`, and `base_link → lidar_link` transforms with a ruler while everything's off the robot — those go straight into the URDF (see [`software.md`](software.md)).

## Known issues / to-do

- ~~No encoders on the motors — odometry today is open-loop.~~ **Fixed:** the two rear motors were swapped for encoded versions, so odometry is now closed-loop (one encoder per side, feeding `diff_drive_controller` via `mibot_hardware`).
- Front motors are still unmodded TT motors — if the front wheel slips on a rug and the rear (encoded) wheel doesn't, odometry still thinks the robot moved. Not a real issue on flat floors; would be on rough terrain.
- Motor battery holder is 4×AA — voltage sags fast under load. A small 2S Li-ion pack would be more honest.
- No bumper / IMU yet — fusing an IMU with the encoder odometry via `robot_localization` is the next accuracy upgrade.

## References

- [Articulated Robotics — Building a Mobile Robot playlist](https://youtube.com/playlist?list=PLunhqkrRNRhYAffV8JDiFOatQXuU-NnxT) — the reference build. The parts choices above are heavily informed by that series.
- L298N datasheet — search "L298N dual H-bridge module".
- Raspberry Pi 4 GPIO pinout — `pinout` command on the Pi, or [pinout.xyz](https://pinout.xyz).
