# External Physics and Flight-Dynamics Simulators

This note surveys **external** physics/flight-dynamics options for ArduPilot
SITL and PX4 SITL. It does not count ArduPilot's built-in dynamics or PX4's
built-in SIH model. A simulator's graphical viewer alone is not necessarily a
physics backend. Availability and supported vehicle models depend on the
simulator, bridge, and autopilot release; the options below are research leads,
not blanket compatibility claims for this repository's images. The project-owned
JSBSim adapters are the exception with scoped installed checks linked below;
upstream JSBSim connector support is not the same integration.

For the proposed four runtime profiles, image/service boundaries, clock/reset
contracts and qualification experiments, see
[RUNTIME_PROFILES.md](RUNTIME_PROFILES.md). This page remains the backend catalog;
that note captures the integration design and research handoff.

| Simulator or FDM | ArduPilot | PX4 | Typical use |
| --- | --- | --- | --- |
| [Gazebo (modern)](https://ardupilot.org/dev/docs/sitl-with-gazebo.html) | Documented external simulator with ArduPilot integration | [Core-supported](https://docs.px4.io/main/en/sim_gazebo_gz/) through PX4's Gazebo bridge | Robot dynamics, worlds, collisions, and rich sensor simulation |
| [JSBSim](https://ardupilot.org/dev/docs/sitl-with-jsbsim.html) | Documented external FDM | [Community-supported](https://docs.px4.io/main/en/sim_jsbsim/) | Configurable aircraft dynamics, especially fixed-wing; PX4 also documents quad and hex models |
| [X-Plane](https://ardupilot.org/dev/docs/sitl-with-xplane.html) | Documented commercial simulator backend | [Community-supported bridge](https://docs.px4.io/main/en/sim_xplane/) | Aircraft models and graphical simulation |
| [PteroSim](https://ardupilot.org/dev/docs/sitl-with-pterosim.html) | Unreal-based backend using ArduPilot's JSON interface | [Community-supported](https://docs.px4.io/main/en/sim_pterosim/) | UAV dynamics and visualization; proprietary licensing/tier limits apply |
| FlightGear | ArduPilot's [standard SITL `--enable-fgview` setup](https://ardupilot.org/dev/docs/setting-up-sitl-on-linux.html) is **view-only**, not an external FDM | [Community-supported simulator integration](https://docs.px4.io/main/en/sim_flightgear/) | PX4 aircraft/weather simulation; distinguish its integration from FlightGear-as-viewer |
| AirSim | [Archived ArduPilot integration](https://ardupilot.org/dev/docs/sitl-with-airsim.html) | [Community-supported integration](https://docs.px4.io/main/en/sim_airsim/) | Unreal-based scenes and visual sensors; check release compatibility |

Additional options:

- **ArduPilot:** [Webots](https://ardupilot.org/dev/docs/sitl-with-webots.html)
  (documented multirotor and rover examples),
  [RealFlight](https://ardupilot.org/dev/docs/sitl-with-realflight.html)
  (commercial), [last_letter](https://ardupilot.org/dev/docs/using-last_letter-as-an-external-sitl-simulator.html)
  (fixed-wing), and [MATLAB/Simulink](https://ardupilot.org/dev/docs/MATLAB-Simulink-Simulation.html).
  The [JSON/UDP interface](https://ardupilot.org/dev/docs/sitl-with-JSON.html)
  is a **protocol for connecting a custom physics backend**, not an FDM itself.
- **PX4:** [RotorPy](https://docs.px4.io/main/en/sim_rotorpy/) is a
  community-supported Python multirotor simulation environment. PX4 also
  documents [Gazebo Classic](https://docs.px4.io/main/en/sim_gazebo_classic/),
  but recommends modern Gazebo for new work.

## Choosing an integration

The first experimental pairing is ArduCopter + JSBSim F450 through a project-owned
JSON-physics adapter, not the native fixed-wing-oriented JSBSim connector. It has
combined and optional separate simulator packaging; see [ARDUCOPTER_JSBSIM.md](ARDUCOPTER_JSBSIM.md) for
usage and exact qualification status. Catalog support does not establish that
an arbitrary aircraft/release combination works. [PX4 + JSBSim](PX4_JSBSIM.md)
now uses the same catalog through a separate simulator-MAVLink adapter; pinned
v1.16.0 combined/split flight checks pass without rebuilding PX4.

- For a shared external-simulator *platform*, start by evaluating modern
  Gazebo: both autopilots document integrations, but each needs its own bridge,
  vehicle configuration, and actuator/sensor mappings.
- For configurable aircraft flight dynamics, evaluate JSBSim; PX4 labels its
  integration community-supported, so verify against the intended release.
- Do not infer that a common FDM means a common wire protocol. ArduPilot's
  generic JSON/UDP interface, PX4's simulator MAVLink API, and PX4's Gazebo
  bridge are distinct. PX4 SIH instead runs internally over uORB; it is **not**
  an external backend.
- The primary Docker images package prebuilt ArduPilot SITL and PX4 SIH runtimes.
  JSBSim supports combined and split images; other external stacks are not packaged. The PX4 SIH build intentionally skips their
  dependencies (see [PX4 SIH runtime](PX4_SIH.md)). Running an external backend
  requires the appropriate simulator, integration/build path, connectivity,
  and matched model configuration; it is not enabled by selecting a different
  SIH model environment variable.

Sources and support-status starting points:
[ArduPilot simulation overview](https://ardupilot.org/dev/docs/simulation-2.html),
[PX4 simulation overview](https://docs.px4.io/main/en/simulation/), and
[PX4 community-supported simulators](https://docs.px4.io/main/en/simulation/community_supported_simulators).
