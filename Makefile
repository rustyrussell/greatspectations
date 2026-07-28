check:
	uv run pytest

upload:
	rsync -va web/ ozlabs.org:www/greatspectations.org/
