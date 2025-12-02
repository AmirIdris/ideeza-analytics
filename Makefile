.PHONY: build up down seed test logs precalc

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

seed:
	docker-compose exec web python manage.py seed_data

migrate:
	docker-compose exec web python manage.py migrate

test:
	docker-compose exec web python manage.py test

shell:
	docker-compose exec web python manage.py shell

precalc:
	docker-compose exec web python manage.py precalculate_stats