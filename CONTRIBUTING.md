# How to Contribute

We'd love to accept your patches and contributions to this project. There are just a few small guidelines you need to follow.

## Development Setup

This project uses modern Python tooling:

- **[mise](https://mise.jdx.dev/)** - manages tool versions
- **[uv](https://docs.astral.sh/uv)** - fast Python package manager

### Bootstrapping the project

```bash
# Install mise and project tools
source <(mise activate bash)  # or zsh, fish, etc. # optional if mise is not already sourced
mise install

# Install Python dependencies
uv venv && source .venv/bin/activate
uv sync --all-groups
```

### Available tasks

```bash
mise run  # Shows all available tasks
mise run lint-fix && mise run format  # Fix code style
mise run test-unittest  # Run unit tests
mise run test-integration  # Run integration tests (requires cluster)
```

## Development Rules

- This project follows [semantic versioning](https://semver.org/)
- All Pull requests should follow semantic versioning rules
- All changes should include tests when applicable (Python, Helm, etc.)
- All Pull requests should include a description of changes and rationale
- Python code uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting

## Making Changes

1. **Create a branch** from `main` with a descriptive name
2. **Make your changes** following the code style
3. **Add tests** for new functionality
4. **Run tests** to ensure everything works
5. **Format code**: `mise run format && mise run lint-fix`
6. **Submit a PR** with clear description

## Testing

### Unit Tests

Fast tests that don't need external dependencies:

```bash
mise run test-unittest
```

### Integration Tests

End-to-end tests that create a KinD cluster with PostgreSQL:

```bash
mise run test-integration
```

### Test with coverage report

```bash
mise run test-and-coverage
```

**Note:** Integration tests will create/destroy a KinD cluster and can take several minutes.

## Code Style

- Use **type hints** for function parameters and return values
- Write **docstrings** for public functions and classes
- Keep functions **small and focused**
- Use **meaningful variable names**
- Handle errors with appropriate `kopf.TemporaryError` or `kopf.PermanentError`

Example error handling:

```python
try:
    result = await database_operation()
except RetryableError as e:
    raise kopf.TemporaryError(f"Will retry: {e}", delay=30)
except PermanentError as e:
    raise kopf.PermanentError(f"Cannot retry: {e}")
```

## Pull Request Process

### Before submitting

- [ ] Code is formatted (`mise run format`)
- [ ] Linting passes (`mise run lint`)
- [ ] Tests pass (`mise run test-and-coverage`)
- [ ] Changes are documented

### PR Description

Include:

- **Summary** of what the PR does
- **List of changes** made
- **Testing** performed
- **Documentation** updates (if needed)

## Project Structure

```
src/userinit/           # Main application code
├── config.py          # Configuration and constants
├── connections.py     # Database connection management
├── database.py        # Database operations
├── models.py          # Data models and parsing
└── userinit.py        # Main Kopf event handlers
src/tests/             # Test suite
charts/crunchy-userinit/  # Helm chart
```

## Code Reviews

All submissions require review. We use GitHub pull requests for this purpose. Consult [GitHub Help](https://help.github.com/articles/about-pull-requests/) for more information on using pull requests.

## Getting Help

- Check existing [issues](https://github.com/DrummyFloyd/crunchy-userinit-controller/issues)
- Look at test examples for usage patterns
- Ask questions in issue discussions
