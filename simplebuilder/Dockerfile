ARG BASE_IMAGE=debian:13
FROM ${BASE_IMAGE}

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Update and install
RUN apt-get update && \
    # Core build tools
    apt-get install -y \
        build-essential \
        devscripts \
        debhelper \
        dh-make \
        fakeroot \
        equivs \
        cdbs \
        quilt && \
    # Package management and building
    apt-get install -y \
        dpkg-dev \
        lintian \
        debian-archive-keyring \
        debootstrap \
        pbuilder \
        sbuild \
        cowbuilder && \
    # Version control
    apt-get install -y \
        git \
        git-buildpackage \
        subversion \
        mercurial && \
    # Compression and archiving
    apt-get install -y \
        gzip \
        bzip2 \
        xz-utils \
        zip \
        unzip \
        tar \
        pristine-tar && \
    # Network and utilities
    apt-get install -y \
        wget \
        curl \
        gnupg \
        apt-transport-https \
        ca-certificates \
        lsb-release \
        sudo \
        vim \
        less \
        bash-completion && \
    # Build systems
    apt-get install -y \
        cmake \
        automake \
        autoconf \
        libtool \
        pkg-config \
        meson \
        ninja-build \
        maven && \
    # Language support
    apt-get install -y \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        python3-setuptools \
        ruby \
        ruby-dev \
        golang \
        nodejs \
        npm \
        dh-sequence-phpcomposer \
        phpab \
        phpunit \
        default-jdk \
        libmaven-compiler-plugin-java \
        libsurefire-java \
        libmaven-jar-plugin-java \
        libmaven-resources-plugin-java \
        libmaven-dependency-tree-java && \
    # Libraries often needed
    apt-get install -y \
        libssl-dev \
        zlib1g-dev \
        libncurses5-dev \
        libreadline-dev \
        libyaml-dev \
        libffi-dev \
        libgdbm-dev \
        libxml2-dev \
        libxslt1-dev \
        libcurl4-openssl-dev \
        libpq-dev \
        gnome-common \
        libatk1.0-dev \
        libatk-bridge2.0-dev \
        libatspi2.0-dev \
        libdbus-1-dev \
        libglib2.0-dev && \
    # Clean up
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

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