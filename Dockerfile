FROM python:3.12

# Define build arguments to fix the undefined variable warnings
ARG GIT_HASH=unknown
ARG BUILD_DATE=unknown

# Add cross-compilation support
ARG TARGETPLATFORM
ARG BUILDPLATFORM
ARG TARGETOS
ARG TARGETARCH

# Copy source code and requirements
COPY ./src /src
COPY ./requirements.txt /src/requirements.txt

# Install Python dependencies
RUN pip install -r /src/requirements.txt

# Create user and set permissions
RUN adduser --system --no-create-home controller
RUN chmod +x /src/entrypoint.sh

# Switch to non-root user
USER controller

# Set the entrypoint
CMD ["/src/entrypoint.sh"]

# Add metadata labels
LABEL org.opencontainers.image.version=${GIT_HASH}
LABEL org.opencontainers.image.created=${BUILD_DATE}
LABEL org.opencontainers.image.documentation="https://github.com/Ramblurr/crunchy-userinit-controller"
LABEL org.opencontainers.image.source="https://github.com/Ramblurr/crunchy-userinit-controller"
LABEL org.opencontainers.image.vendor="@ramblurr"
