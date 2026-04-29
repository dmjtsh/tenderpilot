.PHONY: migrate run worker beat shell install

install:
	pip install -r requirements/dev.txt

migrate:
	python manage.py migrate

run:
	python manage.py runserver

worker:
	celery -A config worker -l info

beat:
	celery -A config beat -l info

shell:
	python manage.py shell_plus

parse:
	python manage.py parse_eis --days=$(or $(days),7)

index:
	python manage.py index_tenders
