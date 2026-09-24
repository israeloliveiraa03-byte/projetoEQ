#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
atualizar_dados.py — Escolas Quilombolas em Dados (CONAQ · Coletivo de Educação)
================================================================================

Baixa a planilha pública do Google Sheets com o recorte quilombola do Censo
Escolar (tabela "Escola", escolas em comunidades quilombolas), limpa os dados,
recupera as coordenadas geográficas e regenera o index.html do painel a partir
de template.html — mesma arquitetura do painel Raizame Dados.

Uso local (requer só Python 3.9+ e internet, nada para instalar):
    python3 atualizar_dados.py                 # baixa a planilha configurada
    python3 atualizar_dados.py --csv escolas.csv   # usa um CSV local (teste ou planilha privada)
    python3 atualizar_dados.py --forcar        # ignora a trava de queda brusca no total de escolas

Arquivos esperados no mesmo diretório:
    template.html   -> painel com os placeholders __DATA_JSON__ etc.

Gera:
    index.html      -> painel pronto para publicar.
"""

import argparse
import csv
import difflib
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# ----------------------------------------------------------------------
# CONFIGURAÇÃO — preencha quando criar a planilha online (ver README.md)
# ----------------------------------------------------------------------
SHEET_ID = os.environ.get("SHEET_ID") or "COLE_AQUI_O_ID_DA_PLANILHA"   # docs.google.com/spreadsheets/d/<ESTE_ID>/edit
GID = os.environ.get("GID") or "0"                                       # número da aba com os dados (ver README)
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"
LINK_PLANILHA = os.environ.get("LINK_PLANILHA") or ""                    # link público da planilha (seção Fontes)

MUNICIPIOS_URL = "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv"

TEMPLATE_PATH = "template.html"
OUTPUT_PATH = "index.html"

SO_QUILOMBOLAS = True      # mantém apenas os códigos abaixo em TP_LOCALIZACAO_DIFERENCIADA
CODIGOS_QUILOMBOLAS = {3}  # 3 = área remanescente de quilombo. Confira no dicionário do INEP do ano se outros
                           # códigos também identificam quilombos; se sim, inclua-os aqui e ajuste o texto de
                           # metodologia do template.
MINIMO_REGISTROS = int(os.environ.get("MINIMO_REGISTROS", "200"))   # trava de segurança contra download quebrado
QUEDA_MAXIMA = 0.30        # aborta se a base encolher mais que isso em relação ao painel publicado
TOLERANCIA_GRAUS = 3.0     # coordenada a mais que isso do centróide do município é tratada como suspeita

# ----------------------------------------------------------------------
# MAPEAMENTO: coluna do Censo -> campo interno do painel
# Se o INEP/planilha renomear uma coluna, o script avisa no log em vez de
# quebrar; basta ajustar o nome aqui.
# ----------------------------------------------------------------------
CAMPOS = {
    # ----- identificação e localização -----
    'NU_ANO_CENSO': 'ano', 'NO_REGIAO': 'regiao', 'NO_UF': 'ufNome', 'SG_UF': 'uf',
    'NO_MUNICIPIO': 'municipio', 'CO_MUNICIPIO': 'ibge',
    'NO_ENTIDADE': 'escola', 'CO_ENTIDADE': 'cod',
    'TP_DEPENDENCIA': 'dep', 'TP_LOCALIZACAO': 'loc',
    'TP_LOCALIZACAO_DIFERENCIADA': 'locDif', 'TP_SITUACAO_FUNCIONAMENTO': 'sit',
    'DS_ENDERECO': 'endereco', 'NO_BAIRRO': 'bairro',
    'LATITUDE': 'latTxt', 'LONGITUDE': 'lonTxt',
    # ----- água / energia / esgoto / lixo -----
    'IN_AGUA_POTAVEL': 'aguaPotavel', 'IN_AGUA_REDE_PUBLICA': 'aguaRede',
    'IN_AGUA_CACIMBA': 'aguaCacimba', 'IN_AGUA_FONTE_RIO': 'aguaFonte',
    'IN_AGUA_CARRO_PIPA': 'aguaPipa', 'IN_AGUA_INEXISTENTE': 'aguaInexistente',
    'IN_ENERGIA_REDE_PUBLICA': 'energiaRede', 'IN_ENERGIA_RENOVAVEL': 'energiaRenovavel',
    'IN_ENERGIA_INEXISTENTE': 'energiaInexistente',
    'IN_ESGOTO_REDE_PUBLICA': 'esgotoRede', 'IN_ESGOTO_FOSSA': 'esgotoFossa',
    'IN_ESGOTO_INEXISTENTE': 'esgotoInexistente',
    'IN_LIXO_SERVICO_COLETA': 'lixoColeta', 'IN_LIXO_QUEIMA': 'lixoQueima',
    # ----- dependências físicas -----
    'IN_BANHEIRO': 'banheiro', 'IN_BANHEIRO_PNE': 'banheiroPne',
    'IN_BANHEIRO_CHUVEIRO': 'banheiroChuveiro', 'IN_BIBLIOTECA_SALA_LEITURA': 'biblioteca',
    'IN_COZINHA': 'cozinha', 'IN_DESPENSA': 'despensa', 'IN_REFEITORIO': 'refeitorio',
    'IN_LABORATORIO_CIENCIAS': 'labCiencias', 'IN_LABORATORIO_INFORMATICA': 'labInfo',
    'IN_PATIO_COBERTO': 'patioCoberto', 'IN_PATIO_DESCOBERTO': 'patioDescoberto',
    'IN_PARQUE_INFANTIL': 'parqueInfantil', 'IN_QUADRA_ESPORTES': 'quadra',
    'IN_SALA_DIRETORIA': 'salaDiretoria', 'IN_SALA_LEITURA': 'salaLeitura',
    'IN_SALA_PROFESSOR': 'salaProfessor', 'IN_SECRETARIA': 'secretaria',
    'IN_SALA_ATENDIMENTO_ESPECIAL': 'salaAee', 'IN_AREA_VERDE': 'areaVerde',
    'IN_AREA_PLANTIO': 'areaPlantio', 'IN_DORMITORIO_ALUNO': 'dormitorioAluno',
    # ----- acessibilidade -----
    'IN_ACESSIBILIDADE_CORRIMAO': 'accCorrimao', 'IN_ACESSIBILIDADE_ELEVADOR': 'accElevador',
    'IN_ACESSIBILIDADE_PISOS_TATEIS': 'accPisosTateis', 'IN_ACESSIBILIDADE_VAO_LIVRE': 'accVaoLivre',
    'IN_ACESSIBILIDADE_RAMPAS': 'accRampas', 'IN_ACESSIBILIDADE_SINAL_TATIL': 'accSinalTatil',
    'IN_ACESSIBILIDADE_SINAL_VISUAL': 'accSinalVisual', 'IN_ACESSIBILIDADE_SINALIZACAO': 'accSinalizacao',
    'IN_ACESSIBILIDADE_INEXISTENTE': 'accInexistente',
    # ----- salas e equipamentos -----
    'QT_SALAS_UTILIZADAS': 'salas', 'QT_SALAS_UTILIZA_CLIMATIZADAS': 'salasClimatizadas',
    'QT_SALAS_UTILIZADAS_ACESSIVEIS': 'salasAcessiveis',
    'IN_EQUIP_PARABOLICA': 'equipParabolica', 'IN_COMPUTADOR': 'temComputador',
    'IN_EQUIP_TV': 'temTV', 'IN_EQUIP_MULTIMIDIA': 'temMultimidia',
    'IN_EQUIP_LOUSA_DIGITAL': 'temLousa',
    'QT_DESKTOP_ALUNO': 'desktops', 'QT_COMP_PORTATIL_ALUNO': 'notebooks', 'QT_TABLET_ALUNO': 'tablets',
    # ----- internet -----
    'IN_INTERNET': 'internet', 'IN_INTERNET_ALUNOS': 'internetAlunos',
    'IN_INTERNET_COMUNIDADE': 'internetComunidade', 'IN_BANDA_LARGA': 'bandaLarga',
    # ----- profissionais -----
    'QT_PROF_ADMINISTRATIVOS': 'profAdministrativo', 'QT_PROF_SERVICOS_GERAIS': 'profServicos',
    'QT_PROF_BIBLIOTECARIO': 'profBibliotecario', 'QT_PROF_SAUDE': 'profSaude',
    'QT_PROF_COORDENADOR': 'profCoordenador', 'QT_PROF_FONAUDIOLOGO': 'profFonoaudiologo',
    'QT_PROF_NUTRICIONISTA': 'profNutricionista', 'QT_PROF_PSICOLOGO': 'profPsicologo',
    'QT_PROF_ALIMENTACAO': 'profAlimentacao', 'QT_PROF_PEDAGOGIA': 'profPedagogo',
    'QT_PROF_SECRETARIO': 'profSecretario', 'QT_PROF_SEGURANCA': 'profSeguranca',
    'QT_PROF_MONITORES': 'profMonitor', 'QT_PROF_GESTAO': 'profGestao',
    'QT_PROF_ASSIST_SOCIAL': 'profAssistenteSocial', 'QT_PROF_TRAD_LIBRAS': 'profLibras',
    'QT_PROF_AGRICOLA': 'profAgricola', 'QT_PROF_REVISOR_BRAILLE': 'profBraille',
    # ----- alimentação e materiais -----
    'IN_ALIMENTACAO': 'alimentacao', 'IN_MATERIAL_PED_QUILOMBOLA': 'matQuilombola',
    'IN_MATERIAL_PED_ETNICO': 'matEtnico', 'IN_MATERIAL_PED_CAMPO': 'matCampo',
    'IN_MATERIAL_PED_INDIGENA': 'matIndigena', 'IN_MATERIAL_PED_MULTIMIDIA': 'matMultimidia',
    'IN_MATERIAL_PED_CIENTIFICO': 'matCientifico',
    # ----- participação e gestão -----
    'IN_ORGAO_CONSELHO_ESCOLAR': 'conselhoEscolar', 'IN_ORGAO_ASS_PAIS_MESTRES': 'assocPais',
    'IN_ORGAO_GREMIO_ESTUDANTIL': 'gremio', 'IN_EDUC_AMBIENTAL': 'educAmbiental',
    # ----- oferta / etapas -----
    'IN_ESPECIAL_EXCLUSIVA': 'especialExclusiva', 'IN_PROFISSIONALIZANTE': 'profissionalizante',
    'IN_COMUM_CRECHE': 'creche', 'IN_COMUM_PRE': 'preEscolar',
    'IN_COMUM_FUND_AI': 'fundAI', 'IN_COMUM_FUND_AF': 'fundAF',
    'IN_COMUM_MEDIO_MEDIO': 'medio', 'IN_COMUM_MEDIO_INTEGRADO': 'medioIntegrado',
    'IN_COMUM_EJA_FUND': 'ejaFund', 'IN_COMUM_EJA_MEDIO': 'ejaMedio',
}

TEXTO = {'ano', 'regiao', 'ufNome', 'uf', 'municipio', 'ibge', 'escola', 'cod', 'latTxt', 'lonTxt'}

PROFS = ['profAdministrativo', 'profServicos', 'profBibliotecario', 'profSaude',
         'profCoordenador', 'profFonoaudiologo', 'profNutricionista', 'profPsicologo',
         'profAlimentacao', 'profPedagogo', 'profSecretario', 'profSeguranca',
         'profMonitor', 'profGestao', 'profAssistenteSocial', 'profLibras',
         'profAgricola', 'profBraille']
INTEIROS = {'salas', 'salasClimatizadas', 'salasAcessiveis', 'desktops',
            'notebooks', 'tablets', 'dep', 'loc', 'locDif', 'sit'} | set(PROFS)

ACC_BRUTOS = ('accCorrimao', 'accElevador', 'accPisosTateis', 'accVaoLivre',
              'accRampas', 'accSinalTatil', 'accSinalVisual', 'accSinalizacao',
              'accInexistente')


# ----------------------------------------------------------------------
# UTILITÁRIOS
# ----------------------------------------------------------------------
def baixar_texto(url):
    if not re.match(r'^[a-z][a-z0-9+.-]*://', url):      # caminho de arquivo local (--csv)
        with open(url, encoding='utf-8-sig', newline='') as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": "escolas-quilombolas-bot/1.0"})
    for tentativa in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return resp.read().decode("utf-8-sig")
        except urllib.error.HTTPError as e:
            if e.code < 500:      # 403/404: repetir não adianta (planilha privada, ID ou GID errados)
                raise RuntimeError(f"HTTP {e.code} ao baixar {url.split('?')[0]}. Confira o SHEET_ID/GID e se a planilha "
                                   "está compartilhada como 'Qualquer pessoa com o link'.") from e
            if tentativa == 3:
                raise
            print(f"  falha no download ({e}); nova tentativa {tentativa + 1}/3…")
            time.sleep(5 * tentativa)
        except Exception as e:
            if tentativa == 3:
                raise
            print(f"  falha no download ({e}); nova tentativa {tentativa + 1}/3…")
            time.sleep(5 * tentativa)


def para_bin(v):
    n = para_int(v)
    return n if n in (0, 1) else None


def para_int(v):
    if v is None:
        return None
    v = v.strip()
    if not v or v == '*':
        return None
    try:
        n = int(float(v.replace(',', '.')))
    except ValueError:
        return None
    if n >= 88888:      # código de "não informado" usado pelo INEP
        return None
    return n


# ----------------------------------------------------------------------
# GEOCODIFICAÇÃO
# ----------------------------------------------------------------------
def recupera_coord(txt, ref, e_lat):
    """
    Recupera a coordenada a partir do texto da planilha.

    O Censo traz latitude/longitude como '-2.491758333'. Quando esses valores
    são colados numa planilha em português, o ponto é interpretado como
    separador de milhar e o número vira o inteiro -2491758333 (exibido como
    '-2,491,758,333'). Aqui recolocamos a vírgula decimal: testamos 1 ou 2
    dígitos na parte inteira e escolhemos o candidato que cai na faixa
    geográfica correta e mais perto do centróide do município (referência).
    """
    if not txt:
        return None
    s = str(txt).strip().replace('°', '').replace(' ', '')
    if s in ('', '*'):
        return None
    neg = s.startswith('-')
    digitos = re.sub(r'\D', '', s)
    if not digitos:
        return None

    def faixa_ok(x):
        return (-35.5 <= x <= 6.0) if e_lat else (-75.0 <= x <= -30.0)

    # 1) o texto já é uma coordenada válida (ex.: '-2.491758' ou '-2,491758')
    try:
        direto = float(s.replace(',', '.'))
        if faixa_ok(direto):
            return direto
    except ValueError:
        pass

    # 2) inteiro corrompido: recolocamos o ponto decimal. Candidatos = 1 ou 2 dígitos na parte inteira; para
    #    latitudes entre 0 e -1 (Amapá/Pará) o zero inicial some, então também testamos "0,xxxx" (o INEP usa 9 casas).
    ref_alvo = (ref[0] if e_lat else ref[1]) if ref else None
    candidatos = []
    for k in ((1, 2) if e_lat else (2, 1)):
        if len(digitos) > k:
            candidatos.append(int(digitos[:k]) + int(digitos[k:]) / (10 ** (len(digitos) - k)))
    if e_lat:
        for casas in sorted({len(digitos), 9}):
            if casas >= len(digitos):
                candidatos.append(int(digitos) / 10 ** casas)

    melhor, melhor_dist = None, None
    for cand in candidatos:
        if neg:
            cand = -cand
        if not faixa_ok(cand):
            continue
        if ref_alvo is None:
            return cand
        dist = abs(cand - ref_alvo)
        if dist <= TOLERANCIA_GRAUS and (melhor_dist is None or dist < melhor_dist):
            melhor, melhor_dist = cand, dist
    return melhor


def carrega_municipios():
    print(f"Baixando centróides municipais: {MUNICIPIOS_URL}")
    por_codigo = {}
    for linha in csv.DictReader(io.StringIO(baixar_texto(MUNICIPIOS_URL))):
        por_codigo[linha['codigo_ibge']] = (float(linha['latitude']), float(linha['longitude']))
    print(f"{len(por_codigo)} municípios carregados.")
    return por_codigo


def geocodifica(registros, por_codigo):
    sem_geo = suspeitas = 0
    for r in registros:
        ref = por_codigo.get(r.get('ibge'))
        lat = recupera_coord(r.get('latTxt'), ref, True)
        lon = recupera_coord(r.get('lonTxt'), ref, False)
        if ref and lat is not None and lon is not None and \
                (abs(lat - ref[0]) > TOLERANCIA_GRAUS or abs(lon - ref[1]) > TOLERANCIA_GRAUS):
            suspeitas += 1          # ponto longe demais do próprio município: provável erro de digitação
            lat = lon = None
        if lat is not None and lon is not None:
            r['lat'], r['lon'], r['fonteGeo'] = round(lat, 6), round(lon, 6), 'escola'
        elif ref:
            r['lat'], r['lon'], r['fonteGeo'] = round(ref[0], 4), round(ref[1], 4), 'municipio'
        else:
            r['lat'], r['lon'], r['fonteGeo'] = None, None, 'nenhuma'
            sem_geo += 1
    if suspeitas:
        print(f"AVISO: {suspeitas} coordenada(s) muito distantes do município foram descartadas (uso do centróide).")
    print(f"Georreferenciamento: {sum(1 for r in registros if r['fonteGeo']=='escola')} pela própria coordenada, "
          f"{sum(1 for r in registros if r['fonteGeo']=='municipio')} por centróide municipal, {sem_geo} sem localização.")
    return sem_geo


# ----------------------------------------------------------------------
# LEITURA DA PLANILHA
# ----------------------------------------------------------------------
def baixa_escolas(fonte=None):
    fonte = fonte or CSV_URL
    print(f"Lendo planilha: {fonte}")
    texto = baixar_texto(fonte)
    if texto.lstrip()[:15].lower().startswith(('<!doctype', '<html')):
        raise RuntimeError("O Google devolveu uma página HTML em vez do CSV: confira se a planilha está compartilhada como "
                           "'Qualquer pessoa com o link' (leitor) e se o GID é o da aba certa.")
    linhas = list(csv.reader(io.StringIO(texto)))
    if not linhas:
        raise RuntimeError("Planilha vazia ou inacessível (confira se ela está pública).")

    cabecalho = [h.replace('\xa0', ' ').strip() for h in linhas[0]]
    indice, faltando = {}, []
    for coluna, campo in CAMPOS.items():
        if coluna in cabecalho:
            indice[campo] = cabecalho.index(coluna)
        else:
            faltando.append(coluna)
    if faltando:
        print("AVISO: colunas ausentes na planilha (campos ficarão 'sem dado'):")
        for c in faltando:
            parecida = difflib.get_close_matches(c, cabecalho, n=1, cutoff=0.8)
            print(f"  - {c}" + (f"   (parecida na planilha: {parecida[0]})" if parecida else ""))
    criticas = ['NO_ENTIDADE', 'CO_ENTIDADE', 'CO_MUNICIPIO', 'SG_UF'] + (['TP_LOCALIZACAO_DIFERENCIADA'] if SO_QUILOMBOLAS else [])
    ausentes = [c for c in criticas if c not in cabecalho]
    if ausentes:
        raise RuntimeError(f"A planilha não parece ser a tabela de Escolas do Censo (faltam colunas essenciais: {ausentes}). "
                           "Confira se o link está público e se a aba certa foi indicada em GID.")

    registros, excluidas, duplicadas, por_cod = [], 0, 0, {}
    for linha in linhas[1:]:
        if not any(c.strip() for c in linha):
            continue

        def bruto(campo):
            i = indice.get(campo)
            if i is None or i >= len(linha):
                return ''
            return (linha[i] or '').replace('\xa0', '').strip()

        if bruto('escola') in ('', '*'):
            continue
        if SO_QUILOMBOLAS and para_int(bruto('locDif')) not in CODIGOS_QUILOMBOLAS:
            excluidas += 1
            continue
        r = {}
        for coluna, campo in CAMPOS.items():
            if campo in ('latTxt', 'lonTxt'):
                r[campo] = bruto(campo)
            elif campo in TEXTO:
                v = bruto(campo)
                if campo in ('ibge', 'cod') and v:      # '1505008.0' ou '1.505.008' -> '1505008'
                    v = re.sub(r'\.0+$', '', v)
                    v = re.sub(r'\D', '', v)
                r[campo] = v if v not in ('', '*') else None
            elif campo in INTEIROS:
                r[campo] = para_int(bruto(campo))
            else:
                r[campo] = para_bin(bruto(campo))

        # campos derivados
        recursos = [r.get(c) for c in ACC_BRUTOS if c != 'accInexistente']
        if 1 in recursos:
            r['acess'] = 1
        elif r.get('accInexistente') == 1 or 0 in recursos:
            r['acess'] = 0
        else:
            r['acess'] = None
        profs = [r.get(c) for c in PROFS]
        informados = [p for p in profs if p is not None]
        r['profTotal'] = sum(informados) if informados else None

        # mesma escola em mais de uma linha (ex.: anos diferentes): fica a do Censo mais recente
        chave = r.get('cod')
        if chave and chave in por_cod:
            duplicadas += 1
            i = por_cod[chave]
            if (r.get('ano') or '') > (registros[i].get('ano') or ''):
                registros[i] = r
            continue
        if chave:
            por_cod[chave] = len(registros)
        registros.append(r)

    print(f"{len(registros)} escolas lidas ({excluidas} fora do recorte quilombola, {duplicadas} linhas repetidas da mesma escola descartadas).")
    ufs = {}
    for r in registros:
        ufs[r['uf'] or '—'] = ufs.get(r['uf'] or '—', 0) + 1
    print("Por UF: " + ", ".join(f"{uf}={n}" for uf, n in sorted(ufs.items())))
    return registros


# ----------------------------------------------------------------------
# GERAÇÃO DO index.html
# ----------------------------------------------------------------------
def hoje_br():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime('%d/%m/%Y')
    except Exception:
        return datetime.now().strftime('%d/%m/%Y')


def le_publicado():
    """Hash e total do painel já publicado (meta tags do index.html), se existir."""
    try:
        with open(OUTPUT_PATH, encoding='utf-8') as f:
            html = f.read(6000)
    except OSError:
        return None, None
    h = re.search(r'name="dados-hash" content="([0-9a-f]+)"', html)
    n = re.search(r'name="dados-total" content="(\d+)"', html)
    return (h.group(1) if h else None), (int(n.group(1)) if n else None)


def gera_pagina(registros, sem_geo):
    with open(TEMPLATE_PATH, encoding='utf-8') as f:
        tpl = f.read()

    # JSON compacto, sem campos vazios (o template trata ausente = sem dado)
    enxutos = [{k: v for k, v in r.items() if v is not None} for r in registros]
    dados = json.dumps(enxutos, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    dados = dados.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')

    # dicionário campo interno -> coluna do INEP, usado pelo botão "Base completa em CSV"
    ocultos = {'latTxt', 'lonTxt', 'endereco', 'bairro', 'ufNome', *ACC_BRUTOS}
    campos = {campo: coluna for coluna, campo in CAMPOS.items() if campo not in ocultos}
    campos.update({'lat': 'LATITUDE_TRATADA', 'lon': 'LONGITUDE_TRATADA', 'fonteGeo': 'ORIGEM_COORDENADA',
                   'acess': 'ACESSIBILIDADE_ALGUM_RECURSO (derivado)', 'profTotal': 'PROFISSIONAIS_TOTAL (derivado)'})
    campos_json = json.dumps(campos, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')

    # o hash cobre dados + template + link: se nada mudou, não regeneramos (e não há commit)
    h = hashlib.sha256((tpl + dados + campos_json + str(sem_geo) + LINK_PLANILHA).encode('utf-8')).hexdigest()[:16]
    h_antigo, _ = le_publicado()
    if h == h_antigo:
        print("Sem alterações nos dados nem no template: index.html mantido como está.")
        return False

    municipios = len({r['ibge'] for r in registros if r['ibge']})
    ufs = len({r['uf'] for r in registros if r['uf']})
    anos = sorted({r['ano'] for r in registros if r['ano']})
    ano = anos[-1] if anos else '—'
    nota_geo = (f"Nesta geração, {sem_geo} escola(s) sem coordenada nem município identificável ficaram fora do mapa."
                if sem_geo else "Todas as escolas desta base puderam ser posicionadas no mapa.")

    subs = {
        '__TOTAL_ESCOLAS__': f'{len(registros):,}'.replace(',', '.'),
        '__TOTAL_MUNICIPIOS__': f'{municipios:,}'.replace(',', '.'),
        '__TOTAL_UFS__': str(ufs),
        '__TOTAL_BRUTO__': str(len(registros)),
        '__HASH_DADOS__': h,
        '__ANO_CENSO__': str(ano),
        '__NAO_GEOCODIFICADOS__': nota_geo,
        '__DATA_GERACAO__': hoje_br(),
        '__LINK_PLANILHA__': LINK_PLANILHA or '#',
    }
    for k, v in subs.items():
        tpl = tpl.replace(k, v)
    restantes = re.findall(r'__[A-Z_]+__', tpl.replace('__DATA_JSON__', '').replace('__CAMPOS_JSON__', ''))
    if restantes:
        raise RuntimeError(f"Placeholders não substituídos: {restantes}")
    tpl = tpl.replace('__CAMPOS_JSON__', campos_json).replace('__DATA_JSON__', dados)   # por último: o JSON nunca passa pelas outras trocas

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(tpl)
    print(f"{OUTPUT_PATH} gerado com {len(registros)} escolas.")
    return True


def main():
    ap = argparse.ArgumentParser(description="Regenera o index.html do painel a partir da planilha.")
    ap.add_argument("--csv", help="caminho local (ou URL) de um CSV, no lugar da planilha configurada")
    ap.add_argument("--forcar", action="store_true", help="ignora a trava de queda brusca no total de escolas")
    args = ap.parse_args()

    if not args.csv and SHEET_ID.startswith("COLE_AQUI"):
        print("ERRO: preencha SHEET_ID (no topo do script ou como variável de ambiente) ou use --csv. Veja o README.")
        sys.exit(1)

    try:
        registros = baixa_escolas(args.csv)
        if len(registros) < MINIMO_REGISTROS:
            raise RuntimeError(
                f"só vieram {len(registros)} registros (mínimo esperado: {MINIMO_REGISTROS}). "
                f"{OUTPUT_PATH} não foi alterado. Se o recorte é menor de propósito, ajuste MINIMO_REGISTROS.")
        _, total_antigo = le_publicado()
        if not args.forcar and total_antigo and len(registros) < total_antigo * (1 - QUEDA_MAXIMA):
            raise RuntimeError(
                f"a base caiu de {total_antigo} para {len(registros)} registros (mais de {int(QUEDA_MAXIMA * 100)}%). "
                f"{OUTPUT_PATH} não foi alterado. Se a queda é legítima, rode com --forcar.")

        por_codigo = carrega_municipios()
        sem_geo = geocodifica(registros, por_codigo)

        # remove campos de trabalho (não vão para o JSON público)
        for r in registros:
            for c in ('latTxt', 'lonTxt', 'endereco', 'bairro', 'ufNome') + ACC_BRUTOS:
                r.pop(c, None)

        gera_pagina(registros, sem_geo)
    except (RuntimeError, OSError) as e:      # OSError cobre falhas de rede/arquivo
        print(f"ERRO: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
