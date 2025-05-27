run:
	uv run server.py

snowman.png:
	curl -fsSL https://huggingface.co/microsoft/kosmos-2-patch14-224/resolve/main/snowman.png -o snowman.png

curl-test: snowman.png
	curl -X POST -F "content=@snowman.png" http://127.0.0.1:8010/stats | jq

client-test:
	uv run client.py

requirements.txt: pyproject.toml
	uv pip compile pyproject.toml -o requirements.txt

build: Dockerfile requirements.txt
	docker buildx build --platform linux/amd64,linux/arm64 -t imagestats-api .

docker-run: build
	docker run --rm -ti -p 8010:8010 imagestats-api