run:
	uv run server.py

lint:
	uvx black .
	uvx isort --profile black .
	uvx ruff check .
	uvx ty check

snowman.png:
	curl -fsSL https://huggingface.co/microsoft/kosmos-2-patch14-224/resolve/main/snowman.png -o snowman.png

curl-test: snowman.png
	curl -X POST -F "content=@snowman.png" http://127.0.0.1:8010/stats | jq

client-test:
	uv run client.py | jq

requirements.txt: pyproject.toml
	uv pip compile pyproject.toml -o requirements.txt

push: Dockerfile requirements.txt
	docker buildx build --platform linux/amd64,linux/arm64 -t mindthemath/imagestats-api:latest . --push

build: Dockerfile requirements.txt
	docker build -t mindthemath/imagestats-api:latest .

docker-run: build
	docker run --rm -ti -p 8010:8010 -e WORKERS_PER_DEVICE=8 mindthemath/imagestats-api:latest
