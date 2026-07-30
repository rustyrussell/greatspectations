.PHONY: check check-types ci examples upload publish

check:
	uv run pytest

check-types:
	uv run mypy

ci: check check-types

examples:
	uv run python examples/generate.py

upload:
	rsync -va web/ ozlabs.org:www/greatspectations.org/

# Refuses unless HEAD is exactly a clean, tagged v<version> commit
# matching pyproject.toml -- publishing to PyPI can't be undone, so
# there must be no ambiguity about what's being published.
publish: ci
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "error: working tree is not clean" >&2; exit 1; \
	fi
	@tag=$$(git describe --tags --exact-match 2>/dev/null); \
	if [ -z "$$tag" ]; then \
		echo "error: HEAD is not exactly on a tag" >&2; exit 1; \
	fi; \
	ver="v$$(uv version --short)"; \
	if [ "$$tag" != "$$ver" ]; then \
		echo "error: tag $$tag does not match pyproject.toml version $$ver" >&2; exit 1; \
	fi
	rm -rf dist
	uv build
	uv publish
