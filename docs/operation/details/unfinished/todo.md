# TODO



- [ ] create a script for just reinitializzing the controller with a modified script
- [ ] check the OpenLoad tool, to measure response time.
- [ ] check for mongodb articles (try to see for cdn, data distribution, data popularity and data trends) on google scolar and iee.
- [ ] Ao inves de tentar dar handle da decisao de que storage utilizar para cada pedido que é feito, deixa-se um conjunto de storages possiveis de se utilizar no server container e vai-se atualizando esse mapeamento consoante o estado da rede
- [ ] Maybe pourposefully lower the mongodb instance storage capability right away in order to see variance in preenchimento
- [ ] se calhar utilizar o mongodb arbitro para as cenas de aggregação
- [ ] se calhar para cada rede que o controlador recebe ele assume qual é o aggregator a qque deve estar conectado tambem
- [ ] quando houver dados ver como utilizar snapshots assim os replicasets começam com dados
- [ ] The code under is for instead of going directly to a replicaset you can just cache the hot collections.

def_hot_collections(client: MongoClient) -> list[str]:

    """Return collection names with recent read or write activity."""

    try:

    result=client.admin.command("top")

    totals=result.get("totals", {})

    active= [

    nsforns, statsintotals.items()

    ifns!="note"

    and (stats.get("readLock", {}).get("count", 0) >0

    orstats.get("writeLock", {}).get("count", 0) >0)

    ]

    returnactive

    except PyMongoError:

    return []
