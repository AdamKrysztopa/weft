#!/bin/zsh
# Exit A (43.5): from the built wheel, outside the repository, against a throwaway database.
# run_exit_a.sh REPEAT BACKEND(pg|qdrant) CORPUS_DIR — one repeat; the caller loops.
# WEFT_VENV names a venv holding weft-rag[openai,qdrant,pdf] installed from the built wheel;
# the published run used the first 100 PDFs of Open RAGBench by name, symlinked into CORPUS_DIR.
set -u
REPEAT=$1 BACKEND=$2 CORPUS=$3
HERE=${0:A:h}; REPO=$(git -C $HERE rev-parse --show-toplevel)
NAME=exita_${BACKEND}_${REPEAT}
DB=weft_${NAME}; COLL=${NAME}
BASE=$(grep '^WEFT_DATABASE_URL=' $REPO/.env | cut -d= -f2- | sed 's#/weft$##')
VENV=${WEFT_VENV:?set WEFT_VENV to the venv holding the built wheel}
A=$HERE/runs/$NAME; rm -rf $A; mkdir -p $A/pipelines
cp $REPO/eval/experiments/pipelines/index-openai-large-pdf.yaml $A/pipelines/
[[ $BACKEND == qdrant ]] && cp $HERE/index-openai-large-pdf-qdrant.yaml $A/pipelines/
PIPE=index-openai-large-pdf; [[ $BACKEND == qdrant ]] && PIPE=index-openai-large-pdf-qdrant
STORE_LINE=""; [[ $BACKEND == qdrant ]] && STORE_LINE='store = "qdrant"'

docker exec weft-postgres-1 psql -U weft -d weft -qc "CREATE DATABASE $DB" || exit 9
echo "$DB $COLL" >> $HERE/created.txt
cat > $A/weft.toml <<T
[packs.store]
dsn = "$BASE/$DB"
[packs.qdrant]
collection = "$COLL"
vector_size = 3072
[packs.openai]
api_key = "\${env:OPENAI_API_KEY}"
[llm.roles]
generate = { provider = "openai", model = "gpt-5.6-luna" }
[services]
embed = "openai-embeddings"
$STORE_LINE
[services.embed_config]
model = "text-embedding-3-large"
T

sysctl -n vm.loadavg > $A/load_before.txt
docker exec weft-postgres-1 psql -U weft -d $DB -Atc "select count(*) from weft_nodes" > $A/rows_before.txt 2>&1

cd $A
# (1) and (4) come from the index's own progress lines; (2), (3) and (5) from the ask loop.
( while true; do
    T=$(python3 -c 'import time;print(f"{time.time():.3f}")')
    OUT=$($VENV/bin/weft ask --pipeline retrieve-then-generate "$(cat $HERE/question_first.txt)" 2>&1)
    print -r -- "{\"t\": $T, \"q\": \"first\", \"exit\": $?, \"out\": $(python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))' <<< "$OUT")}"
    T=$(python3 -c 'import time;print(f"{time.time():.3f}")')
    OUT=$($VENV/bin/weft ask --pipeline retrieve-then-generate "$(cat $HERE/question_last.txt)" 2>&1)
    print -r -- "{\"t\": $T, \"q\": \"last\", \"exit\": $?, \"out\": $(python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))' <<< "$OUT")}"
    sleep 5
  done ) > $A/asks.jsonl 2>$A/asks.err &
ASKER=$!

START=$(python3 -c 'import time;print(f"{time.time():.3f}")')
echo "$START" > $A/start.txt
$VENV/bin/weft index $CORPUS --pipeline $PIPE > $A/index.out 2> $A/index.err
echo "INDEX_EXIT=$?" > $A/index_exit.txt
echo "$(python3 -c 'import time;print(f"{time.time():.3f}")')" > $A/end.txt
sleep 6
kill $ASKER 2>/dev/null

# the same two asks after the run, for (5)'s "against the same after"
for i in 1 2 3 4 5 6 7 8 9 10; do
  T=$(python3 -c 'import time;print(f"{time.time():.3f}")')
  $VENV/bin/weft ask --pipeline retrieve-then-generate "$(cat $HERE/question_first.txt)" > /dev/null 2>&1
  python3 -c "import time;print(f'{time.time()-$T:.3f}')"
done > $A/after_latencies.txt

sysctl -n vm.loadavg > $A/load_after.txt
docker exec weft-postgres-1 psql -U weft -d $DB -Atc "select 'nodes', count(*) from weft_nodes union all select 'sources_'||status, count(*) from weft_sources group by status" > $A/rows_after.txt 2>&1
[[ $BACKEND == qdrant ]] && python3 -c "import urllib.request,json;print('qdrant_points', json.load(urllib.request.urlopen('http://localhost:6333/collections/$COLL'))['result']['points_count'])" >> $A/rows_after.txt
cat $A/index_exit.txt $A/rows_after.txt
