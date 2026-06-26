# syntax=docker/dockerfile:1.4
ARG BASE_IMAGE="ubuntu"
ARG TAG="24.04"

FROM ${BASE_IMAGE}:${TAG} AS builder
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG DEBIAN_FRONTEND=noninteractive
ARG USER_NAME=ardupilot
ARG USER_UID=1000
ARG USER_GID=1000
ARG ARDUPILOT_REPO=https://github.com/ArduPilot/ardupilot.git
ARG ARDUPILOT_REF=master
ARG COPTER_TAG=
ARG ARDUPILOT_CLONE_DEPTH=1
ARG WAF_TARGET=
ARG WAF_ALL_TARGETS="copter plane rover sub"
ARG WAF_JOBS=2
ARG SKIP_AP_EXT_ENV=0
ARG SKIP_AP_GRAPHIC_ENV=1
ARG SKIP_AP_COV_ENV=1
ARG SKIP_AP_GIT_CHECK=1
ARG DO_AP_STM_ENV=0

WORKDIR /${USER_NAME}

RUN set -eux; \
    existing_group="$(getent group "${USER_GID}" | cut -d: -f1 || true)"; \
    if [ -n "$existing_group" ]; then \
        if [ "$existing_group" != "${USER_NAME}" ]; then \
            groupmod -n "${USER_NAME}" "$existing_group"; \
        fi; \
    else \
        groupadd "${USER_NAME}" --gid "${USER_GID}"; \
    fi; \
    existing_user="$(getent passwd "${USER_UID}" | cut -d: -f1 || true)"; \
    if [ -n "$existing_user" ]; then \
        if [ "$existing_user" != "${USER_NAME}" ]; then \
            usermod -l "${USER_NAME}" -d "/home/${USER_NAME}" -m "$existing_user"; \
        fi; \
    else \
        useradd -l -m "${USER_NAME}" -u "${USER_UID}" -g "${USER_GID}" -s /bin/bash; \
    fi

RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install --no-install-recommends -y \
    ca-certificates \
    git \
    lsb-release \
    openjdk-17-jre-headless \
    sudo \
    tzdata

# Ensure Gradle uses a supported JDK when building Java-based ArduPilot tools.
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

RUN echo "${USER_NAME} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${USER_NAME} \
    && chmod 0440 /etc/sudoers.d/${USER_NAME} \
    && chown -R ${USER_NAME}:${USER_NAME} /home/${USER_NAME} /${USER_NAME}

USER ${USER_NAME}
WORKDIR /home/${USER_NAME}

# Micro-XRCE-DDS-Gen is a build-time dependency for newer ArduPilot trees.
# Keep it before the ArduPilot checkout so changing ARDUPILOT_REF does not
# invalidate the Gradle dependency cache.
RUN --mount=type=cache,target=/home/${USER_NAME}/.gradle,sharing=locked,uid=${USER_UID},gid=${USER_GID} \
    git clone --recurse-submodules --depth 1 --branch v4.7.1 https://github.com/ardupilot/Micro-XRCE-DDS-Gen.git /home/${USER_NAME}/Micro-XRCE-DDS-Gen \
    && cd /home/${USER_NAME}/Micro-XRCE-DDS-Gen \
    && ./gradlew assemble

RUN set -eux; \
    ref="${COPTER_TAG:-${ARDUPILOT_REF}}"; \
    depth_args=""; \
    if [ -n "${ARDUPILOT_CLONE_DEPTH}" ]; then \
        depth_args="--depth ${ARDUPILOT_CLONE_DEPTH}"; \
    fi; \
    if git clone ${depth_args} --branch "$ref" "${ARDUPILOT_REPO}" ardupilot; then \
        :; \
    else \
        git clone "${ARDUPILOT_REPO}" ardupilot; \
        cd ardupilot; \
        git checkout "$ref"; \
        cd ..; \
    fi; \
    cd ardupilot; \
    git config --global --add safe.directory /home/${USER_NAME}/ardupilot

WORKDIR /home/${USER_NAME}/ardupilot

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,target=/home/${USER_NAME}/.cache/pip,sharing=locked,uid=${USER_UID},gid=${USER_GID} \
    SKIP_AP_EXT_ENV=${SKIP_AP_EXT_ENV} \
    SKIP_AP_GRAPHIC_ENV=${SKIP_AP_GRAPHIC_ENV} \
    SKIP_AP_COV_ENV=${SKIP_AP_COV_ENV} \
    SKIP_AP_GIT_CHECK=${SKIP_AP_GIT_CHECK} \
    DO_AP_STM_ENV=${DO_AP_STM_ENV} \
    DO_PYTHON_VENV_ENV=1 \
    AP_DOCKER_BUILD=1 \
    USER=${USER_NAME} \
    Tools/environment_install/install-prereqs-ubuntu.sh -y

RUN echo "if [ -d \"\$HOME/.local/bin\" ] ; then" >> /home/${USER_NAME}/.ardupilot_env \
    && echo "    export PATH=\"\$HOME/.local/bin:\$PATH\"" >> /home/${USER_NAME}/.ardupilot_env \
    && echo "fi" >> /home/${USER_NAME}/.ardupilot_env \
    && echo "export PATH=\$PATH:/home/${USER_NAME}/Micro-XRCE-DDS-Gen/scripts" >> /home/${USER_NAME}/.ardupilot_env \
    && echo "alias waf=\"\$HOME/ardupilot/waf\"" >> /home/${USER_NAME}/.bashrc

RUN set -eux; \
    submodule_depth_args=""; \
    if [ -n "${ARDUPILOT_CLONE_DEPTH}" ]; then \
        submodule_depth_args="--depth ${ARDUPILOT_CLONE_DEPTH}"; \
    fi; \
    git submodule update --init --recursive ${submodule_depth_args}

# Pre-build SITL binaries so the runtime image starts quickly with --no-rebuild.
RUN --mount=type=cache,target=/home/${USER_NAME}/.ccache,sharing=locked,uid=${USER_UID},gid=${USER_GID} \
    source /home/${USER_NAME}/.ardupilot_env \
    && python3 -m pip show empy \
    && if [ -n "${WAF_TARGET}" ]; then \
        case "${WAF_TARGET}" in copter|plane|rover|sub) build_targets="${WAF_TARGET}" ;; *) echo "Unsupported WAF_TARGET=${WAF_TARGET}; expected one of: copter, plane, rover, sub" >&2; exit 1 ;; esac; \
    else \
        build_targets="${WAF_ALL_TARGETS}"; \
    fi \
    && ./waf configure --board sitl \
    && for target in ${build_targets}; do ./waf -j "${WAF_JOBS}" "${target}"; done

# Drop source-control metadata and transient build files before copying into
# the runtime stage. The checked-out source and built SITL artifacts remain.
RUN rm -rf \
    /home/${USER_NAME}/ardupilot/.git \
    /home/${USER_NAME}/ardupilot/modules/*/.git \
    /home/${USER_NAME}/.cache \
    /home/${USER_NAME}/Micro-XRCE-DDS-Gen/.git


FROM ${BASE_IMAGE}:${TAG} AS runtime
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG DEBIAN_FRONTEND=noninteractive
ARG USER_NAME=ardupilot
ARG USER_UID=1000
ARG USER_GID=1000

WORKDIR /${USER_NAME}

RUN set -eux; \
    existing_group="$(getent group "${USER_GID}" | cut -d: -f1 || true)"; \
    if [ -n "$existing_group" ]; then \
        if [ "$existing_group" != "${USER_NAME}" ]; then \
            groupmod -n "${USER_NAME}" "$existing_group"; \
        fi; \
    else \
        groupadd "${USER_NAME}" --gid "${USER_GID}"; \
    fi; \
    existing_user="$(getent passwd "${USER_UID}" | cut -d: -f1 || true)"; \
    if [ -n "$existing_user" ]; then \
        if [ "$existing_user" != "${USER_NAME}" ]; then \
            usermod -l "${USER_NAME}" -d "/home/${USER_NAME}" -m "$existing_user"; \
        fi; \
    else \
        useradd -l -m "${USER_NAME}" -u "${USER_UID}" -g "${USER_GID}" -s /bin/bash; \
    fi

RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install --no-install-recommends -y \
    bash \
    ca-certificates \
    libpython3-stdlib \
    libxml2 \
    libxslt1.1 \
    netbase \
    ppp \
    procps \
    python3 \
    python3-pexpect \
    screen

RUN install -d -m 0755 /usr/local/bin /configs \
    && chown -R ${USER_NAME}:${USER_NAME} /home/${USER_NAME} /${USER_NAME}

COPY --from=builder --chown=${USER_NAME}:${USER_NAME} /home/${USER_NAME}/ardupilot /home/${USER_NAME}/ardupilot
COPY --from=builder --chown=${USER_NAME}:${USER_NAME} /home/${USER_NAME}/venv-ardupilot /home/${USER_NAME}/venv-ardupilot
COPY --from=builder --chown=${USER_NAME}:${USER_NAME} /home/${USER_NAME}/.ardupilot_env /home/${USER_NAME}/.ardupilot_env
COPY --from=builder --chown=${USER_NAME}:${USER_NAME} /home/${USER_NAME}/Micro-XRCE-DDS-Gen/scripts /home/${USER_NAME}/Micro-XRCE-DDS-Gen/scripts
COPY docker/resolve-sitl-config.py /usr/local/bin/resolve-sitl-config.py
COPY docker/install-sitl-lua.sh /usr/local/bin/install-sitl-lua.sh

RUN printf '%s\n' \
        'source ~/.ardupilot_env' \
        > /home/${USER_NAME}/.bashrc \
    && chown ${USER_NAME}:${USER_NAME} /home/${USER_NAME}/.bashrc \
    && printf '%s\n' \
        '#!/bin/bash' \
        'set -e' \
        "source /home/${USER_NAME}/.ardupilot_env" \
        'if [ "$#" -eq 0 ]; then' \
        '    exec /usr/local/bin/run-sitl.sh' \
        'fi' \
        'if [ "${1#-}" != "$1" ]; then' \
        '    exec /usr/local/bin/run-sitl.sh "$@"' \
        'fi' \
        'exec "$@"' \
        > /usr/local/bin/ardupilot_entrypoint.sh \
    && printf '%s\n' \
        '#!/bin/bash' \
        'set -e' \
        "cd /home/${USER_NAME}/ardupilot" \
        'extra_args=()' \
        '/usr/local/bin/install-sitl-lua.sh' \
        'if [ "${NO_MAVPROXY:-0}" = "1" ]; then' \
        '    extra_args+=(--no-mavproxy)' \
        'fi' \
        'if [ -n "${PROXY:-}" ]; then' \
        '    extra_args+=(-m "${PROXY}")' \
        'fi' \
        'mapfile -t config_args < <(/usr/local/bin/resolve-sitl-config.py)' \
        'extra_args+=("${config_args[@]}")' \
        'exec Tools/autotest/sim_vehicle.py -j "${JOBS:-2}" --vehicle "${VEHICLE}" --frame "${FRAME}" -I "${INSTANCE}" --sysid "${SYSID}" --custom-location="${LAT},${LON},${ALT},${DIR}" -w --no-rebuild --speedup "${SPEEDUP}" "${extra_args[@]}" "$@"' \
        > /usr/local/bin/run-sitl.sh \
    && chmod +x /usr/local/bin/ardupilot_entrypoint.sh /usr/local/bin/run-sitl.sh /usr/local/bin/resolve-sitl-config.py /usr/local/bin/install-sitl-lua.sh

USER ${USER_NAME}
WORKDIR /home/${USER_NAME}/ardupilot

ENV BUILDLOGS=/tmp/buildlogs
ENV CCACHE_MAXSIZE=1G
ENV PATH="/home/${USER_NAME}/.local/bin:/home/${USER_NAME}/venv-ardupilot/bin:${PATH}"

# TCP 5760 is the default SITL connection. MAVProxy opens its own default
# outputs unless overridden with sim_vehicle.py args or PROXY.
# EXPOSE 14550/udp
# EXPOSE 14551/udp
# EXPOSE 5760/tcp
# EXPOSE 5761/tcp

ENV INSTANCE=0
ENV SYSID=1
ENV LAT=37.1971467
ENV LON=-80.5780381
ENV ALT=618
ENV DIR=55
ENV VEHICLE=ArduCopter
ENV FRAME=quad
ENV SPEEDUP=1
ENV NO_MAVPROXY=0
ENV SITL_CONFIG_DIR=/configs
ENV VEHICLEINFO_JSON=
ENV MODEL=
ENV PARAM_FILE=
ENV LUA_SCRIPT=

ENTRYPOINT ["/usr/local/bin/ardupilot_entrypoint.sh"]
