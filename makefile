run:
	uv run server.py

snowman.png:
	curl -fsSL https://huggingface.co/microsoft/kosmos-2-patch14-224/resolve/main/snowman.png -o snowman.png

curl-test: snowman.png
	curl -X POST -F "content=@snowman.png" http://127.0.0.1:8001/stats | jq

client-test:
	uv run client.py
