snowman.png:
	curl -fsSL https://huggingface.co/microsoft/kosmos-2-patch14-224/resolve/main/snowman.png -o snowman.png

test:
	curl -X POST -F "content=@/Users/mm/Pictures/NJH/20211001_113221.jpg" http://127.0.0.1:8001/stats | jq

client:
	uv run client.py
