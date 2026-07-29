.PHONY: check examples upload

check:
	uv run pytest

examples:
	uv run python examples/generate.py

upload:
	rsync -va web/ ozlabs.org:www/greatspectations.org/
