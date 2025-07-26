import pandas as pd
import gdown

def carregar_promocoes(path=None):
    if not path:
        # ID do seu arquivo no Google Drive (já exportado como .xlsx)
        file_id = "1tvke4iQnVmbJO34RtGYfaI_KzliSumWH"
        url = f"https://drive.google.com/uc?id={file_id}"
        path = "Promocoes.xlsx"
        gdown.download(url, path, quiet=False)

    promocoes = pd.read_excel(path, sheet_name="promocoes")
    fases = pd.read_excel(path, sheet_name="fases")
    criterios = pd.read_excel(path, sheet_name="criterios_por_hora")
    faixas = pd.read_excel(path, sheet_name="faixas_de_rotas")
    return promocoes, fases, criterios, faixas

def estruturar_promocoes(promocoes, fases, criterios, faixas):
    lista = []

    for _, row in promocoes.iterrows():
        promo = row.to_dict()
        promo["data_inicio"] = pd.to_datetime(promo["data_inicio"]).date()
        promo["data_fim"] = pd.to_datetime(promo["data_fim"]).date()

        tipo = promo["tipo"]
        idp = promo["id"]

        if tipo == "fases":
            fases_rel = fases[fases["id_promocao"] == idp]
            promo["fases"] = [
                {
                    "nome": f["fase_nome"],
                    "inicio": pd.to_datetime(f["data_inicio"]).date(),
                    "fim": pd.to_datetime(f["data_fim"]).date(),
                    "min_rotas": f["min_rotas"]
                }
                for _, f in fases_rel.iterrows()
            ]

        elif tipo == "por_hora":
            crit = criterios[criterios["id_promocao"] == idp].iloc[0]
            promo["criterios"] = {
                "min_pct_online": crit["min_pct_online"],
                "min_aceitacao": crit["min_aceitacao"],
                "min_conclusao": crit["min_conclusao"]
            }

        elif tipo == "faixa_rotas":
            faixas_rel = faixas[faixas["id_promocao"] == idp]
            promo["faixas"] = [
                {
                    "faixa_min": f["faixa_min"],
                    "faixa_max": f["faixa_max"],
                    "valor_premio": f["valor_premio"]
                }
                for _, f in faixas_rel.iterrows()
            ]

        lista.append(promo)

    return lista
