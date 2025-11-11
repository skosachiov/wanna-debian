FROM debian:13

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Update package lists and install essential build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    devscripts \
    debhelper \
    dh-make \
    fakeroot \
    lintian \
    pbuilder \
    git \
    apt-utils \
    && rm -rf /var/lib/apt/lists/*

# Install additional common build dependencies
RUN apt-get update && apt-get install -y \
    autoconf \
    automake \
    libtool \
    pkg-config \
    cmake \
    meson \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for building packages
RUN useradd -m -s /bin/bash builder && \
    echo "builder ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Create working directory
WORKDIR /workspace

# Set ownership to builder user
RUN chown builder:builder /workspace

# Switch to builder user
USER builder

# Default command
CMD ["/bin/bash"]