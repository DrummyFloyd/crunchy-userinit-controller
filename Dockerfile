# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:dc7e1d08f8ca979826ec0b68b31c783e0b35b568be6a078d4cbedf38c4cc085e

WORKDIR /app

ARG BUILD_DATE
ARG GIT_HASH

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
COPY ./pyproject.toml /app
COPY ./uv.lock /app
COPY ./src /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"


ENTRYPOINT ["kopf","run","-m","userinit.userinit"]

# Add metadata labels
LABEL org.opencontainers.image.version=${GIT_HASH}
LABEL org.opencontainers.image.created=${BUILD_DATE}
LABEL org.opencontainers.image.documentation="https://github.com/DrummyFloyd/crunchy-userinit-controller/blob/main/README.md"
LABEL org.opencontainers.image.source="https://github.com/DrummyFloyd/crunchy-userinit-controller"
LABEL org.opencontainers.image.vendor="@drummyfloyd"
