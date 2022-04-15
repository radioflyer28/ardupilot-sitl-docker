FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive
RUN useradd -U -m ardupilot && \
    usermod -G users ardupilot

RUN apt-get update && apt-get install --no-install-recommends -y \
    lsb-release \
    sudo \
    bash-completion \
    software-properties-common \
    git

#COPY Tools/environment_install/install-prereqs-ubuntu.sh /ardupilot/Tools/environment_install/
#COPY Tools/completion /ardupilot/Tools/completion/

# Create non root user for pip
ENV USER=ardupilot

RUN echo "ardupilot ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ardupilot
RUN chmod 0440 /etc/sudoers.d/ardupilot

#RUN chown -R ardupilot:ardupilot /ardupilot

USER ardupilot

# Now grab ArduPilot from GitHub
WORKDIR /home/ardupilot
RUN git clone https://github.com/ArduPilot/ardupilot.git ardupilot
WORKDIR ardupilot

# Checkout the latest Copter...
#ARG COPTER_TAG=Copter-4.1.5
#RUN git checkout ${COPTER_TAG}

# Now start build instructions from http://ardupilot.org/dev/docs/setting-up-sitl-on-linux.html
RUN git submodule update --init --recursive

ENV SKIP_AP_EXT_ENV=1 SKIP_AP_GRAPHIC_ENV=1 SKIP_AP_COV_ENV=1 SKIP_AP_GIT_CHECK=1
RUN Tools/environment_install/install-prereqs-ubuntu.sh -y

# add waf alias to ardupilot waf to .bashrc
RUN echo "alias waf=\"$HOME/ardupilot/waf\"" >> ~/.bashrc

# Continue build instructions from https://github.com/ArduPilot/ardupilot/blob/master/BUILD.md
RUN ./waf distclean
RUN ./waf configure --board sitl
RUN ./waf copter

# Optional builds
#RUN ./waf rover
#RUN ./waf plane
#RUN ./waf sub

# Check that local/bin are in PATH for pip --user installed package
RUN echo "if [ -d \"\$HOME/.local/bin\" ] ; then\nPATH=\"\$HOME/.local/bin:\$PATH\"\nfi" >> ~/.bashrc

# To Mavproxy
ENV PATH PATH=$PATH:/home/ardupilot/.local/bin

# Set the buildlogs directory into /tmp as other directory aren't accessible
ENV BUILDLOGS=/tmp/buildlogs

# Cleanup
RUN sudo apt-get clean \
    && sudo rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ENV CCACHE_MAXSIZE=1G

# TCP 5760 is what the sim exposes by default, 
# 5761 and 5762 are two additional connections for MissionPlanner and a second program
EXPOSE 14550/udp
EXPOSE 14551/udp
EXPOSE 5761/tcp

# Variables for simulator
ENV INSTANCE 0
ENV SYSID 1
ENV LAT 37.1971467
ENV LON -80.5780381
ENV ALT 618
ENV DIR 55
ENV VEHICLE ArduCopter
ENV FRAME quad
ENV SPEEDUP 1

# Extra Mavproxy arguments
ENV PROXY --out=udp:0.0.0.0:14550 --out=tcpin:0.0.0.0:5761

# Finally the command
ENTRYPOINT Tools/autotest/sim_vehicle.py -j 2 --vehicle ${VEHICLE} --frame ${FRAME} -I ${INSTANCE} --sysid ${SYSID} --custom-location=${LAT},${LON},${ALT},${DIR} -w --no-rebuild --speedup ${SPEEDUP} --no-extra-ports -m ${PROXY}
