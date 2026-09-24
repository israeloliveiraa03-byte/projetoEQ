#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
atualizar_dados.py — Escolas Quilombolas em Dados (CONAQ · Coletivo de Educação)
================================================================================

Gera o painel (index.html) a partir dos microdados do Censo Escolar baixados do
INEP. É um script de uso manual: você baixa os CSVs, roda o script, publica o
index.html que sai. Não há automação nem planilha intermediária.

    https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar

Uso (requer só Python 3.9+, nada para instalar):

    python3 atualizar_dados.py --escola Tabela_Escola_2025.csv \\
                               --turma  Tabela_Turma_2025.csv

    --turma é opcional; sem ela, o painel sai sem a seção de EJA.
    --coordenadas é opcional; veja "SOBRE A LOCALIZAÇÃO DAS ESCOLAS" abaixo.

Outras opções:
    --saida painel.html     grava com outro nome
    --so-quilombolas        carrega apenas o código 3 (painel menor, sem comparação)

--------------------------------------------------------------------------------
SOBRE A LOCALIZAÇÃO DAS ESCOLAS
--------------------------------------------------------------------------------
Os microdados públicos do Censo Escolar NÃO trazem latitude e longitude — nem na
tabela de Escola, nem na de Turma. O dado mais fino de localização é o município
(e o distrito, que não tem centróide público fácil de obter).

Por isso, por padrão, o painel não desenha uma escola por ponto: desenha um
círculo por município, com o tamanho proporcional ao número de escolas. Isso é
honesto — é a granularidade que os dados têm. Empilhar 41 escolas de Itapecuru
Mirim no mesmo pixel faria o mapa parecer mais esparso do que a realidade.

Se você conseguir as coordenadas por escola (o Catálogo de Escolas do INEP,
em https://censobasico.inep.gov.br/censobasico/#/ , permite exportar CSV com
latitude e longitude), passe o arquivo em --coordenadas. Ele precisa ter uma
coluna com o código INEP da escola e colunas de latitude e longitude, em
qualquer ordem e com nomes reconhecíveis. Aí o painel desenha escola por escola,
e usa o centróide do município só para as que ficarem sem coordenada.
"""

import argparse
import csv
import difflib
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

csv.field_size_limit(10 ** 9)

# ----------------------------------------------------------------------
# CONFIGURAÇÃO
# ----------------------------------------------------------------------
MUNICIPIOS_URL = "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv"
MUNICIPIOS_CACHE = "municipios-ibge.csv"     # baixado uma vez e reaproveitado (permite rodar offline)

TEMPLATE_PATH = "template.html"
SAIDA_PADRAO = "index.html"

LINK_INEP = "https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar"

# Universo carregado no painel. 3 = quilombola; os outros entram para permitir a
# comparação entre tipos de território (--so-quilombolas deixa só o 3).
UNIVERSO = {1, 2, 3, 8}

MINIMO_REGISTROS = 200     # trava contra CSV truncado ou tabela errada

# Validação de coordenadas. Uma coordenada bem formada é aceita se cair dentro do
# envelope da própria UF (ver caixas_por_uf). O centróide do município entra só para
# desempatar número corrompido — ele não serve como teste de distância, porque há
# municípios amazônicos maiores que países e porque a própria lista de centróides
# tem erros (Pau d'Arco/PA aparece a 750 km do lugar certo).
MARGEM_UF = 2.0            # graus além dos centróides das bordas da UF
TOLERANCIA_GRAUS = 3.0     # só para escolher entre candidatos de um número corrompido

# ----------------------------------------------------------------------
# MAPEAMENTO: coluna do Censo -> campo interno do painel
# Se o INEP renomear uma coluna, o script avisa no log (e sugere a parecida)
# em vez de quebrar; basta ajustar o nome aqui.
# ----------------------------------------------------------------------
CAMPOS_ESCOLA = {
    # ----- identificação e localização -----
    'NU_ANO_CENSO': 'ano', 'NO_REGIAO': 'regiao', 'NO_UF': 'ufNome', 'SG_UF': 'uf',
    'NO_MUNICIPIO': 'municipio', 'CO_MUNICIPIO': 'ibge',
    'NO_ENTIDADE': 'escola', 'CO_ENTIDADE': 'cod',
    'TP_DEPENDENCIA': 'dep', 'TP_LOCALIZACAO': 'loc',
    'TP_LOCALIZACAO_DIFERENCIADA': 'locDif', 'TP_SITUACAO_FUNCIONAMENTO': 'sit',
    # Coordenadas: existem na versão completa da tabela de Escola (colunas AH e AI) e
    # não existem na versão anonimizada (_V2). Quando faltam, o painel agrupa as
    # escolas por município — veja "SOBRE A LOCALIZAÇÃO DAS ESCOLAS" no topo.
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
    'IN_PATIO_COBERTO': 'patioCoberto', 'IN_PARQUE_INFANTIL': 'parqueInfantil',
    'IN_QUADRA_ESPORTES': 'quadra', 'IN_SALA_DIRETORIA': 'salaDiretoria',
    'IN_SALA_LEITURA': 'salaLeitura', 'IN_SALA_PROFESSOR': 'salaProfessor',
    'IN_SECRETARIA': 'secretaria', 'IN_SALA_ATENDIMENTO_ESPECIAL': 'salaAee',
    'IN_AREA_VERDE': 'areaVerde', 'IN_ALMOXARIFADO': 'almoxarifado',
    'IN_DORMITORIO_ALUNO': 'dormitorioAluno',
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
    'IN_INTERNET_ADMINISTRATIVO': 'internetAdm', 'IN_BANDA_LARGA': 'bandaLarga',
    'IN_INTERNET_COMUNIDADE': 'internetComunidade', 'IN_INTERNET_APRENDIZAGEM': 'internetAprendizagem',
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
    'IN_MATERIAL_PED_CIENTIFICO': 'matCientifico', 'IN_MATERIAL_PED_AGRICOLA': 'matAgricola',
    'IN_MATERIAL_PED_NENHUM': 'matNenhum',
    # ----- formação e língua -----
    'IN_EDUCACAO_INDIGENA': 'educIndigena', 'IN_EXAME_SELECAO': 'exameSelecao',
    # ----- participação e gestão -----
    'IN_ORGAO_CONSELHO_ESCOLAR': 'conselhoEscolar', 'IN_ORGAO_ASS_PAIS_MESTRES': 'assocPais',
    'IN_ORGAO_GREMIO_ESTUDANTIL': 'gremio', 'IN_EDUC_AMBIENTAL': 'educAmbiental',
    # ----- modalidades ofertadas (estas SIM dizem o que a escola oferece) -----
    'IN_ESCOLARIZACAO': 'escolarizacao', 'IN_REGULAR': 'regular', 'IN_EJA': 'ofereceEJA',
    'IN_PROFISSIONALIZANTE': 'profissionalizante',
    # ----- educação especial -----
    # ATENÇÃO: os campos IN_COMUM_* e IN_ESP_EXCLUSIVA_* NÃO dizem quais etapas a escola
    # oferece. Eles dizem em que etapa há alunos com deficiência, TEA ou altas habilidades
    # — em classes comuns (COMUM) ou em classe especial exclusiva (ESP_EXCLUSIVA). Uma
    # versão anterior deste painel os usava como "etapas ofertadas", o que estava errado:
    # a etapa ofertada vem da tabela de Turma, abaixo.
    'IN_ESPECIAL_EXCLUSIVA': 'classeEspecial',
    'IN_COMUM_CRECHE': 'espCreche', 'IN_COMUM_PRE': 'espPre',
    'IN_COMUM_FUND_AI': 'espFundAI', 'IN_COMUM_FUND_AF': 'espFundAF',
    'IN_COMUM_MEDIO_MEDIO': 'espMedio',
    'IN_COMUM_EJA_FUND': 'espEjaFund', 'IN_COMUM_EJA_MEDIO': 'espEjaMedio',
}

# Tabela de Turma: quantas turmas a escola efetivamente abriu. É o que mostra o
# tamanho real da oferta — IN_EJA na tabela de Escola só diz sim/não.
CAMPOS_TURMA = {
    'QT_TUR_BAS': 'turTotal',
    'QT_TUR_INF': 'turInf', 'QT_TUR_INF_CRE': 'turCreche', 'QT_TUR_INF_PRE': 'turPre',
    'QT_TUR_FUND': 'turFund', 'QT_TUR_FUND_AI': 'turFundAI', 'QT_TUR_FUND_AF': 'turFundAF',
    'QT_TUR_FUND_AI_MULTIETAPA': 'turFundAIMulti', 'QT_TUR_FUND_AF_MULTI': 'turFundAFMulti',
    'QT_TUR_MED': 'turMed', 'QT_TUR_PROF': 'turProf',
    'QT_TUR_EJA': 'turEja', 'QT_TUR_EJA_FUND': 'turEjaFund', 'QT_TUR_EJA_MED': 'turEjaMed',
    'QT_TUR_EJA_FUND_AI': 'turEjaFundAI', 'QT_TUR_EJA_FUND_AF': 'turEjaFundAF',
    'QT_TUR_EJA_D': 'turEjaDiurno', 'QT_TUR_EJA_N': 'turEjaNoturno', 'QT_TUR_EJA_EAD': 'turEjaEad',
    'QT_TUR_EJA_INT': 'turEjaIntegral',
}

TEXTO = {'ano', 'regiao', 'ufNome', 'uf', 'municipio', 'ibge', 'escola', 'cod', 'latTxt', 'lonTxt'}

PROFS = ['profAdministrativo', 'profServicos', 'profBibliotecario', 'profSaude',
         'profCoordenador', 'profFonoaudiologo', 'profNutricionista', 'profPsicologo',
         'profAlimentacao', 'profPedagogo', 'profSecretario', 'profSeguranca',
         'profMonitor', 'profGestao', 'profAssistenteSocial', 'profLibras',
         'profAgricola', 'profBraille']

INTEIROS = ({'salas', 'salasClimatizadas', 'salasAcessiveis', 'desktops', 'notebooks',
             'tablets', 'dep', 'loc', 'locDif', 'sit'} | set(PROFS) | set(CAMPOS_TURMA.values()))

ACC_BRUTOS = ('accCorrimao', 'accElevador', 'accPisosTateis', 'accVaoLivre',
              'accRampas', 'accSinalTatil', 'accSinalVisual', 'accSinalizacao',
              'accInexistente')

# Campos de trabalho, que não vão para o JSON público.
# latTxt/lonTxt saem porque o que interessa é o lat/lon já tratado.
OCULTOS = ('ufNome', 'latTxt', 'lonTxt') + ACC_BRUTOS

# A versão completa da tabela de Escola traz endereço, CEP e telefone das escolas.
# O painel é uma página pública, e este projeto optou por não republicar esses
# campos; por isso eles nem chegam a ser lidos. Para incluí-los (por exemplo, num
# painel interno do coletivo), acrescente-os a CAMPOS_ESCOLA.
NAO_LIDOS = ('DS_ENDERECO', 'NU_ENDERECO', 'DS_COMPLEMENTO', 'NO_BAIRRO',
             'CO_CEP', 'NU_DDD', 'NU_TELEFONE')

# Colunas que podem faltar sem que isso seja um problema: a versão anonimizada
# dos microdados (_V2) não traz coordenadas.
OPCIONAIS = {'LATITUDE', 'LONGITUDE'}


# ----------------------------------------------------------------------
# LEITURA DE ARQUIVOS
# ----------------------------------------------------------------------
def decodifica(b):
    """Os microdados do INEP vêm em latin-1; exportações de planilha, em UTF-8."""
    for enc in ('utf-8-sig', 'latin-1'):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode('latin-1', errors='replace')


def le_arquivo(caminho):
    if not os.path.exists(caminho):
        raise RuntimeError(f"arquivo não encontrado: {caminho}")
    with open(caminho, 'rb') as f:
        return decodifica(f.read())


def separador(primeira_linha):
    return ';' if primeira_linha.count(';') >= primeira_linha.count(',') else ','


def abre_csv(caminho, rotulo):
    """Devolve (leitor, cabeçalho) já com separador e codificação resolvidos."""
    print(f"Lendo {rotulo}: {caminho}")
    texto = le_arquivo(caminho)
    if not texto.strip():
        raise RuntimeError(f"a {rotulo} está vazia.")
    primeira = texto[:texto.index('\n')] if '\n' in texto else texto
    leitor = csv.reader(io.StringIO(texto), delimiter=separador(primeira))
    cabecalho = [h.replace('\xa0', ' ').strip() for h in next(leitor)]
    return leitor, cabecalho


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


def para_bin(v):
    n = para_int(v)
    return n if n in (0, 1) else None


def so_digitos(v):
    """'1505008.0' ou '1.505.008' -> '1505008'."""
    return re.sub(r'\D', '', re.sub(r'\.0+$', '', (v or '').strip()))


# ----------------------------------------------------------------------
# CENTRÓIDES MUNICIPAIS
# ----------------------------------------------------------------------
def caixas_por_uf(por_codigo):
    """
    Envelope geográfico de cada UF, a partir dos centróides dos seus municípios
    (o código da UF são os dois primeiros dígitos do código do município).

    Serve para validar uma coordenada bem formada sem depender do centróide de UM
    município, que pode estar errado na lista de referência ou ficar muito longe
    da escola em municípios enormes. Altamira (PA) tem 159 mil km²: uma escola
    legítima pode estar a 600 km do centróide. Já uma escola da Bahia com
    coordenada em Roraima continua sendo pega.
    """
    caixas = {}
    for cod, (lat, lon) in por_codigo.items():
        uf = cod[:2]
        c = caixas.setdefault(uf, [lat, lat, lon, lon])
        c[0] = min(c[0], lat); c[1] = max(c[1], lat)
        c[2] = min(c[2], lon); c[3] = max(c[3], lon)
    # margem: o território da UF vai além dos centróides dos municípios das bordas
    return {uf: (a - MARGEM_UF, b + MARGEM_UF, c - MARGEM_UF, d + MARGEM_UF)
            for uf, (a, b, c, d) in caixas.items()}


def carrega_municipios():
    """
    Centróides do IBGE por código de município. Baixa uma vez e guarda em
    MUNICIPIOS_CACHE, para as execuções seguintes funcionarem sem internet.
    """
    texto = None
    if os.path.exists(MUNICIPIOS_CACHE):
        print(f"Centróides municipais: usando o cache local ({MUNICIPIOS_CACHE}).")
        texto = le_arquivo(MUNICIPIOS_CACHE)
    else:
        print(f"Baixando centróides municipais (uma vez só): {MUNICIPIOS_URL}")
        req = urllib.request.Request(MUNICIPIOS_URL, headers={"User-Agent": "escolas-quilombolas/1.0"})
        for tentativa in range(1, 4):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    texto = decodifica(resp.read())
                break
            except Exception as e:
                if tentativa == 3:
                    raise RuntimeError(
                        f"não foi possível baixar os centróides municipais ({e}). Baixe o arquivo à mão "
                        f"de {MUNICIPIOS_URL} e salve como '{MUNICIPIOS_CACHE}' na pasta do script.") from e
                print(f"  falha no download ({e}); nova tentativa {tentativa + 1}/3…")
                time.sleep(5 * tentativa)
        try:
            with open(MUNICIPIOS_CACHE, 'w', encoding='utf-8') as f:
                f.write(texto)
            print(f"  guardado em {MUNICIPIOS_CACHE} (as próximas execuções não precisam de internet).")
        except OSError:
            pass

    por_codigo = {}
    for linha in csv.DictReader(io.StringIO(texto)):
        try:
            por_codigo[linha['codigo_ibge']] = (float(linha['latitude']), float(linha['longitude']))
        except (KeyError, ValueError, TypeError):
            continue
    if not por_codigo:
        raise RuntimeError(f"o arquivo de centróides ({MUNICIPIOS_CACHE}) não tem as colunas esperadas "
                           "(codigo_ibge, latitude, longitude).")
    print(f"{len(por_codigo)} municípios carregados.")
    return por_codigo


# ----------------------------------------------------------------------
# COORDENADAS POR ESCOLA (arquivo opcional)
# ----------------------------------------------------------------------
def acha_coluna(cabecalho, *palavras):
    """Encontra a coluna cujo nome contém uma das palavras (sem acento, maiúsculas)."""
    def normaliza(s):
        s = s.upper()
        for a, b in (('Á', 'A'), ('À', 'A'), ('Ã', 'A'), ('Â', 'A'), ('É', 'E'), ('Ê', 'E'),
                     ('Í', 'I'), ('Ó', 'O'), ('Õ', 'O'), ('Ô', 'O'), ('Ú', 'U'), ('Ç', 'C')):
            s = s.replace(a, b)
        return s
    normal = [normaliza(h) for h in cabecalho]
    for palavra in palavras:
        for i, h in enumerate(normal):
            if palavra in h:
                return i
    return None


def numero_solto(txt):
    """
    Lê uma coordenada que pode vir em vários formatos.

    Além do formato normal ('-2.491758'), trata o caso de a planilha ter lido o
    ponto decimal como separador de milhar, transformando o número no inteiro
    -2491758333. Nesse caso devolvemos os dígitos crus, para que quem chamar
    tente recolocar a vírgula validando contra o município.
    """
    if txt is None:
        return None, None
    s = str(txt).strip().replace('°', '').replace(' ', '')
    if s in ('', '*'):
        return None, None
    direto = None
    try:
        direto = float(s.replace(',', '.'))
    except ValueError:
        pass
    return direto, ('-' if s.startswith('-') else '') + re.sub(r'\D', '', s)


def recupera_coord(txt, ref, e_lat):
    """
    Devolve a coordenada em grau decimal, ou None se não der para confiar.

    Devolve também se o valor veio pronto ou teve que ser reconstruído, no par
    (valor, 'direto' | 'reconstruido' | None).
    """
    direto, digitos = numero_solto(txt)
    if digitos is None:
        return None, None

    def faixa_ok(x):
        return (-35.5 <= x <= 6.0) if e_lat else (-75.0 <= x <= -30.0)

    if direto is not None and faixa_ok(direto):
        return direto, 'direto'

    neg = digitos.startswith('-')
    digitos = digitos.lstrip('-')
    if not digitos:
        return None, None

    # inteiro corrompido: recolocamos o ponto decimal. Candidatos = 1 ou 2 dígitos na parte
    # inteira; para latitudes entre 0 e -1 (Amapá/Pará) o zero inicial some, então também
    # testamos "0,xxxx" (o INEP usa 9 casas decimais).
    ref_alvo = (ref[0] if e_lat else ref[1]) if ref else None
    candidatos = []
    for k in ((1, 2) if e_lat else (2, 1)):
        if len(digitos) > k:
            candidatos.append(int(digitos[:k]) + int(digitos[k:]) / (10 ** (len(digitos) - k)))
    if e_lat:
        for casas in sorted({len(digitos), 9}):
            if casas >= len(digitos):
                candidatos.append(int(digitos) / 10 ** casas)

    # Entre os candidatos válidos, fica o mais próximo do centróide do município.
    # Para coordenadas perto do equador a recuperação é ambígua por natureza:
    # '-15437582' pode ser -0,154 ou -0,0154, e só o município desempata. Em teste
    # com 594 coordenadas corrompidas, 593 voltaram exatas e uma caiu a 7 km da
    # posição real — sempre dentro do município certo, que é o que importa aqui.
    melhor, melhor_dist = None, None
    for cand in candidatos:
        if neg:
            cand = -cand
        if not faixa_ok(cand):
            continue
        if ref_alvo is None:
            return cand, 'reconstruido'
        dist = abs(cand - ref_alvo)
        if dist <= TOLERANCIA_GRAUS and (melhor_dist is None or dist < melhor_dist):
            melhor, melhor_dist = cand, dist
    return melhor, ('reconstruido' if melhor is not None else None)


def le_coordenadas(caminho, por_codigo):
    """Arquivo opcional com coordenadas por escola (ex.: Catálogo de Escolas do INEP)."""
    leitor, cabecalho = abre_csv(caminho, "tabela de coordenadas")
    iCod = acha_coluna(cabecalho, 'CO_ENTIDADE', 'CODIGO INEP', 'CODIGO DA ESCOLA', 'COD_INEP', 'CODIGO')
    iLat = acha_coluna(cabecalho, 'LATITUDE', 'LAT')
    iLon = acha_coluna(cabecalho, 'LONGITUDE', 'LONG', 'LON')
    if iCod is None or iLat is None or iLon is None:
        raise RuntimeError(
            f"a tabela de coordenadas precisa de uma coluna de código INEP, uma de latitude e uma de "
            f"longitude. Encontrei: código={cabecalho[iCod] if iCod is not None else 'nenhuma'}, "
            f"latitude={cabecalho[iLat] if iLat is not None else 'nenhuma'}, "
            f"longitude={cabecalho[iLon] if iLon is not None else 'nenhuma'}.")
    print(f"  colunas usadas: {cabecalho[iCod]}, {cabecalho[iLat]}, {cabecalho[iLon]}")
    fora = {}
    for linha in leitor:
        if max(iCod, iLat, iLon) >= len(linha):
            continue
        cod = so_digitos(linha[iCod])
        if cod:
            fora[cod] = (linha[iLat], linha[iLon])
    print(f"  {len(fora)} escolas com coordenada no arquivo.")
    return fora


# ----------------------------------------------------------------------
# GEOCODIFICAÇÃO
# ----------------------------------------------------------------------
def geocodifica(registros, por_codigo, coords_escola):
    """
    Define lat/lon e fonteGeo de cada escola:
        'escola'    -> coordenada própria (colunas LATITUDE/LONGITUDE da tabela,
                       ou o arquivo passado em --coordenadas, que tem prioridade)
        'municipio' -> centróide do município (quando a escola não tem coordenada)
        'nenhuma'   -> nem uma coisa nem outra; fica fora do mapa
    """
    caixas = caixas_por_uf(por_codigo)
    sem_geo = suspeitas = reconstruidas = 0
    fora_da_uf = []
    for r in registros:
        ref = por_codigo.get(r.get('ibge'))
        lat = lon = None
        # o arquivo externo ganha da coluna da tabela: quem o passou quis corrigir algo
        bruto = (coords_escola.get(r.get('cod')) if coords_escola else None) \
            or ((r.get('latTxt'), r.get('lonTxt')) if r.get('latTxt') and r.get('lonTxt') else None)
        if bruto:
            lat, orig_lat = recupera_coord(bruto[0], ref, True)
            lon, orig_lon = recupera_coord(bruto[1], ref, False)
            if lat is not None and lon is not None:
                caixa = caixas.get((r.get('ibge') or '')[:2])
                if caixa and not (caixa[0] <= lat <= caixa[1] and caixa[2] <= lon <= caixa[3]):
                    suspeitas += 1          # coordenada fora da própria UF: erro de fato
                    if len(fora_da_uf) < 5:
                        fora_da_uf.append(f"{r.get('escola')} ({r.get('municipio')}/{r.get('uf')}): {lat}, {lon}")
                    lat = lon = None
                elif 'reconstruido' in (orig_lat, orig_lon):
                    reconstruidas += 1
        if lat is not None and lon is not None:
            r['lat'], r['lon'], r['fonteGeo'] = round(lat, 6), round(lon, 6), 'escola'
        elif ref:
            r['lat'], r['lon'], r['fonteGeo'] = round(ref[0], 4), round(ref[1], 4), 'municipio'
        else:
            r['lat'], r['lon'], r['fonteGeo'] = None, None, 'nenhuma'
            sem_geo += 1

    proprias = sum(1 for r in registros if r['fonteGeo'] == 'escola')
    mun = sum(1 for r in registros if r['fonteGeo'] == 'municipio')
    if reconstruidas:
        print(f"{reconstruidas} coordenada(s) vieram como inteiro (separador decimal perdido) e foram reconstruídas.")
    if suspeitas:
        print(f"AVISO: {suspeitas} coordenada(s) caíram fora da própria UF e foram descartadas (uso do centróide):")
        for x in fora_da_uf:
            print(f"  - {x}")
        if suspeitas > len(fora_da_uf):
            print(f"  … e mais {suspeitas - len(fora_da_uf)}.")
    print(f"Localização: {proprias} pela coordenada da escola, {mun} pelo centróide do município, {sem_geo} sem localização.")
    n_mun = len({r['ibge'] for r in registros if r.get('fonteGeo') == 'municipio'})
    if proprias == 0:
        print(f"  Esta tabela não traz latitude/longitude, então o mapa mostra {n_mun} círculos (um por")
        print(f"  município), com o tamanho proporcional ao número de escolas. Para ver escola por escola,")
        print(f"  use a versão completa da tabela de Escola ou passe --coordenadas.")
    elif mun:
        print(f"  O mapa mostra {proprias} pontos de escola mais {n_mun} círculo(s) de município, para as")
        print(f"  {mun} escolas sem coordenada própria.")
    return sem_geo, proprias


# ----------------------------------------------------------------------
# LEITURA DAS TABELAS DO CENSO
# ----------------------------------------------------------------------
def mapeia_colunas(cabecalho, campos, criticas, rotulo):
    ausentes = [c for c in criticas if c not in cabecalho]
    if ausentes:
        raise RuntimeError(f"a {rotulo} não parece ser a tabela do Censo: faltam as colunas {ausentes}. "
                           "Confira se o arquivo é o certo e se não foi aberto e salvo por um editor "
                           "que mexeu no cabeçalho.")
    indice, faltando = {}, []
    for coluna, campo in campos.items():
        if coluna in cabecalho:
            indice[campo] = cabecalho.index(coluna)
        else:
            faltando.append(coluna)
    opcionais_ausentes = [c for c in faltando if c in OPCIONAIS]
    faltando = [c for c in faltando if c not in OPCIONAIS]
    if faltando:
        print(f"AVISO: colunas ausentes na {rotulo} (os campos ficarão 'sem dado'):")
        for c in faltando:
            parecida = difflib.get_close_matches(c, cabecalho, n=1, cutoff=0.8)
            print(f"  - {c}" + (f"   (parecida no arquivo: {parecida[0]})" if parecida else ""))
    if 'LATITUDE' in opcionais_ausentes:
        print("  (esta tabela não traz LATITUDE/LONGITUDE — é a versão anonimizada dos microdados. "
              "O mapa vai agrupar as escolas por município.)")
    return indice


def valor(campo, bruto):
    if campo in TEXTO:
        if campo in ('ibge', 'cod'):
            bruto = so_digitos(bruto)
        return bruto if bruto not in ('', '*') else None
    if campo in INTEIROS:
        return para_int(bruto)
    return para_bin(bruto)


def le_escolas(caminho, universo):
    leitor, cabecalho = abre_csv(caminho, "tabela de Escola")
    indice = mapeia_colunas(
        cabecalho, CAMPOS_ESCOLA,
        ['NO_ENTIDADE', 'CO_ENTIDADE', 'CO_MUNICIPIO', 'SG_UF', 'TP_LOCALIZACAO_DIFERENCIADA'],
        "tabela de Escola")
    iLD = cabecalho.index('TP_LOCALIZACAO_DIFERENCIADA')

    registros, fora, repetidas, por_cod = [], 0, 0, {}
    for linha in leitor:
        if not any(c.strip() for c in linha):
            continue
        if len(linha) <= iLD or para_int(linha[iLD]) not in universo:
            fora += 1
            continue

        def bruto(campo):
            i = indice.get(campo)
            if i is None or i >= len(linha):
                return ''
            return (linha[i] or '').replace('\xa0', '').strip()

        if bruto('escola') in ('', '*'):
            continue

        r = {campo: valor(campo, bruto(campo)) for campo in indice}

        # campos derivados
        recursos = [r.get(c) for c in ACC_BRUTOS if c != 'accInexistente']
        if 1 in recursos:
            r['acess'] = 1
        elif r.get('accInexistente') == 1 or 0 in recursos:
            r['acess'] = 0
        else:
            r['acess'] = None
        informados = [r.get(c) for c in PROFS if r.get(c) is not None]
        r['profTotal'] = sum(informados) if informados else None

        # mesma escola em mais de uma linha (ex.: anos diferentes): fica a do Censo mais recente
        chave = r.get('cod')
        if chave and chave in por_cod:
            repetidas += 1
            i = por_cod[chave]
            if (r.get('ano') or '') > (registros[i].get('ano') or ''):
                registros[i] = r
            continue
        if chave:
            por_cod[chave] = len(registros)
        registros.append(r)

    print(f"{len(registros)} escolas no universo ({fora} fora do recorte, {repetidas} linhas repetidas descartadas).")
    return registros


def le_turmas(caminho, registros):
    """Cruza a tabela de Turma pelo código da escola."""
    leitor, cabecalho = abre_csv(caminho, "tabela de Turma")
    indice = mapeia_colunas(cabecalho, CAMPOS_TURMA, ['CO_ENTIDADE'], "tabela de Turma")
    iCO = cabecalho.index('CO_ENTIDADE')
    por_cod = {r['cod']: r for r in registros if r.get('cod')}
    casados = 0
    for linha in leitor:
        if len(linha) <= iCO:
            continue
        r = por_cod.get(so_digitos(linha[iCO]))
        if r is None:
            continue
        for campo, i in indice.items():
            if i < len(linha):
                r[campo] = para_int((linha[i] or '').strip())
        casados += 1
    print(f"Turmas cruzadas para {casados} de {len(registros)} escolas.")
    if casados == 0:
        raise RuntimeError("nenhuma escola casou com a tabela de Turma. As duas tabelas são do mesmo ano?")
    derivados_de_turma(registros)
    return casados


def derivados_de_turma(registros):
    """
    Campos que só fazem sentido depois do cruzamento com a tabela de Turma.

    'multisseriada' importa no recorte quilombola: a maioria dessas escolas junta
    séries diferentes na mesma turma. Quando isso acontece, o Censo costuma lançar
    a turma inteira nos anos finais, então uma escola que ensina do 1º ao 9º ano
    pode aparecer com zero turmas de anos iniciais. Por isso o painel marca a
    escola como multisseriada em vez de fingir que a divisão AI/AF é exata.
    """
    n = 0
    for r in registros:
        fund = r.get('turFund')
        multi = (r.get('turFundAIMulti') or 0) + (r.get('turFundAFMulti') or 0)
        if fund is None:
            r['multisseriada'] = None
        elif multi > 0:
            r['multisseriada'] = 1
            n += 1
        elif fund > 0:
            r['multisseriada'] = 0
        else:
            r['multisseriada'] = None      # escola sem fundamental: a pergunta não se aplica
    print(f"{n} escola(s) com turma multisseriada no ensino fundamental.")


# ----------------------------------------------------------------------
# GERAÇÃO DO PAINEL
# ----------------------------------------------------------------------
def hoje_br():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime('%d/%m/%Y')
    except Exception:
        return datetime.now().strftime('%d/%m/%Y')


def monta_colunar(registros):
    """
    Converte a lista de registros em um pacote colunar: um array por campo, em
    vez de um objeto por escola. O template remonta as linhas ao abrir a página.

    Três codificações, escolhidas por tipo de campo (medido nos dados de 2025,
    12.472 escolas e 123 campos):

        objetos por linha ..... 24,7 MB
        colunar simples ....... 4,3 MB
        colunar como abaixo ... 3,0 MB

      - 'bin'  campos 0/1: viram uma string, um caractere por escola
               ('1' sim, '0' não, '.' sem dado). 70 dos 123 campos são assim, e
               guardá-los como array custaria dois caracteres por escola só de
               vírgula e valor.
      - 'dic'  texto muito repetido (região, UF, município): lista de valores
               distintos + índices.
      - 'num'  o resto: array puro, com null para sem dado.
    """
    campos = []
    for r in registros:
        for c in r:
            if c not in campos and c not in OCULTOS:
                campos.append(c)

    DICIONARIO = {'ano', 'regiao', 'uf', 'municipio', 'fonteGeo'}
    colunas, tipos = {}, {}
    for c in campos:
        vals = [r.get(c) for r in registros]
        if c in DICIONARIO:
            uniq = sorted({v for v in vals if v is not None})
            pos = {v: i for i, v in enumerate(uniq)}
            colunas[c] = {'d': uniq, 'i': [pos[v] if v is not None else -1 for v in vals]}
            tipos[c] = 'dic'
        elif all(v in (0, 1, None) for v in vals):
            colunas[c] = ''.join('1' if v == 1 else ('0' if v == 0 else '.') for v in vals)
            tipos[c] = 'bin'
        else:
            colunas[c] = vals
            tipos[c] = 'num'
    return {'n': len(registros), 'campos': campos, 'tipos': tipos, 'colunas': colunas}


def gera_pagina(registros, sem_geo, proprias, saida, fonte_escola, fonte_turma):
    with open(TEMPLATE_PATH, encoding='utf-8') as f:
        tpl = f.read()

    pacote = monta_colunar(registros)
    dados = json.dumps(pacote, ensure_ascii=False, separators=(',', ':'))
    dados = dados.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')

    campos_inep = {campo: coluna for coluna, campo in
                   list(CAMPOS_ESCOLA.items()) + list(CAMPOS_TURMA.items()) if campo not in OCULTOS}
    campos_inep.update({'lat': 'LATITUDE_USADA', 'lon': 'LONGITUDE_USADA',
                        'fonteGeo': 'ORIGEM_COORDENADA',
                        'acess': 'ACESSIBILIDADE_ALGUM_RECURSO (derivado)',
                        'profTotal': 'PROFISSIONAIS_TOTAL (derivado)'})
    campos_json = json.dumps(campos_inep, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')

    anos = sorted({r['ano'] for r in registros if r.get('ano')})
    ano = anos[-1] if anos else '—'

    # O cabeçalho mostra duas linhas com denominadores diferentes: a do recorte
    # quilombola e a do universo de comparação. Contar municípios/UF sobre o
    # universo e exibi-los na linha das quilombolas seria atribuir a elas uma
    # abrangência que não é delas.
    quilombolas_reg = [r for r in registros if r.get('locDif') == 3]
    quilombolas = len(quilombolas_reg)
    municipios = len({r['ibge'] for r in quilombolas_reg if r.get('ibge')})
    ufs = len({r['uf'] for r in quilombolas_reg if r.get('uf')})
    municipios_universo = len({r['ibge'] for r in registros if r.get('ibge')})
    ufs_universo = len({r['uf'] for r in registros if r.get('uf')})

    if proprias:
        nota_geo = (f"Nesta base, {proprias} escola(s) têm coordenada própria e "
                    f"{sum(1 for r in registros if r['fonteGeo'] == 'municipio')} estão no centróide do município.")
    else:
        nota_geo = ("Os microdados do Censo não trazem latitude e longitude das escolas, então o mapa trabalha "
                    "na granularidade que os dados têm: um círculo por município, proporcional ao número de escolas.")
    if sem_geo:
        nota_geo += f" {sem_geo} escola(s) ficaram sem localização e não aparecem no mapa."

    arquivos = os.path.basename(fonte_escola) + (f" e {os.path.basename(fonte_turma)}" if fonte_turma else "")

    subs = {
        '__TOTAL_ESCOLAS__': f'{quilombolas:,}'.replace(',', '.'),
        '__TOTAL_UNIVERSO__': f'{len(registros):,}'.replace(',', '.'),
        '__TOTAL_MUNICIPIOS__': f'{municipios:,}'.replace(',', '.'),
        '__TOTAL_UFS__': str(ufs),
        '__MUNICIPIOS_UNIVERSO__': f'{municipios_universo:,}'.replace(',', '.'),
        '__UFS_UNIVERSO__': str(ufs_universo),
        '__ANO_CENSO__': str(ano),
        '__NOTA_GEO__': nota_geo,
        '__DATA_GERACAO__': hoje_br(),
        '__ARQUIVOS_FONTE__': arquivos,
        '__LINK_INEP__': LINK_INEP,
    }
    for k, v in subs.items():
        tpl = tpl.replace(k, v)
    restantes = re.findall(r'__[A-Z_]+__', tpl.replace('__DATA_JSON__', '').replace('__CAMPOS_JSON__', ''))
    if restantes:
        raise RuntimeError(f"placeholders não substituídos no template: {restantes}")
    tpl = tpl.replace('__CAMPOS_JSON__', campos_json).replace('__DATA_JSON__', dados)

    with open(saida, 'w', encoding='utf-8') as f:
        f.write(tpl)
    bruto = len(tpl.encode('utf-8'))
    comprimido = len(gzip.compress(tpl.encode('utf-8'), 6))
    print(f"\n{saida} gerado: {len(registros)} escolas ({quilombolas} quilombolas), "
          f"{bruto/1e6:.2f} MB ({comprimido/1e6:.2f} MB quando servido comprimido).")
    print("Abra o arquivo no navegador para conferir, depois publique-o.")


def main():
    ap = argparse.ArgumentParser(
        description="Gera o painel a partir dos microdados do Censo Escolar baixados do INEP.",
        epilog="Exemplo: python3 atualizar_dados.py --escola Tabela_Escola_2025.csv --turma Tabela_Turma_2025.csv")
    ap.add_argument("--escola", required=True, help="CSV da tabela de Escola (obrigatório)")
    ap.add_argument("--turma", help="CSV da tabela de Turma (opcional; habilita a seção de EJA)")
    ap.add_argument("--coordenadas", help="CSV opcional com código INEP, latitude e longitude por escola")
    ap.add_argument("--saida", default=SAIDA_PADRAO, help=f"arquivo a gerar (padrão: {SAIDA_PADRAO})")
    ap.add_argument("--so-quilombolas", action="store_true",
                    help="carrega apenas escolas quilombolas (painel menor, sem comparação entre tipos)")
    args = ap.parse_args()

    universo = {3} if args.so_quilombolas else UNIVERSO

    try:
        if not os.path.exists(TEMPLATE_PATH):
            raise RuntimeError(f"o arquivo {TEMPLATE_PATH} precisa estar na mesma pasta que o script.")

        registros = le_escolas(args.escola, universo)
        if len(registros) < MINIMO_REGISTROS:
            raise RuntimeError(
                f"só vieram {len(registros)} escolas (mínimo esperado: {MINIMO_REGISTROS}). O arquivo pode estar "
                f"truncado ou ser a tabela errada. {args.saida} não foi alterado. Se o recorte é pequeno de "
                f"propósito, ajuste MINIMO_REGISTROS no topo do script.")

        if args.turma:
            le_turmas(args.turma, registros)
        else:
            print("Sem --turma: o painel sairá sem a seção de EJA.")

        por_codigo = carrega_municipios()
        coords = le_coordenadas(args.coordenadas, por_codigo) if args.coordenadas else {}
        sem_geo, proprias = geocodifica(registros, por_codigo, coords)

        for r in registros:
            for c in OCULTOS:
                r.pop(c, None)

        gera_pagina(registros, sem_geo, proprias, args.saida, args.escola, args.turma)
    except (RuntimeError, OSError) as e:
        print(f"\nERRO: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
