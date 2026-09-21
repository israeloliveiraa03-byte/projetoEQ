#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
atualizar_dados.py — Escolas Quilombolas em Dados (CONAQ · Coletivo de Educação)
================================================================================

Baixa a planilha pública do Google Sheets com o recorte quilombola do Censo
Escolar (tabela "Escola"), limpa os dados, recupera as coordenadas geográficas
e regenera o index.html do painel a partir de template.html.

Uso local:
    python3 atualizar_dados.py  (requer apenas internet, sem instalar nada)

Arquivos esperados no mesmo diretório:
    template.html   -> painel com os placeholders __DATA_JSON__ etc.

Gera:
    index.html      -> painel pronto para publicar.
"""

import csv
import io
import json
import re
import sys
import urllib.request
from datetime import datetime

# ----------------------------------------------------------------------
# CONFIGURAÇÃO — já preenchida com a planilha publicada pelo coletivo
# ----------------------------------------------------------------------
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQmkWFZP6JuHSw2GjsquCCwLVhpw0ql0ajb1esJTzk3NUToJZyfaqmMlxXCzxfCuQ/pub?gid=948404274&single=true&output=csv"
LINK_PLANILHA = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQmkWFZP6JuHSw2GjsquCCwLVhpw0ql0ajb1esJTzk3NUToJZyfaqmMlxXCzxfCuQ/pub?gid=948404274&single=true"

MUNICIPIOS_URL = "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv"

TEMPLATE_PATH = "template.html"
OUTPUT_PATH = "index.html"

SO_QUILOMBOLAS = True      # mantém apenas escolas em comunidade quilombola (TP_LOCALIZACAO_DIFERENCIADA = 3)
MINIMO_REGISTROS = 100     # trava de segurança contra download quebrado

# ----------------------------------------------------------------------
# MAPEAMENTO: coluna do Censo -> campo interno do painel
# Se a planilha renomear uma coluna, o script avisa no log em vez de quebrar;
# basta ajustar o nome aqui.
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

TEXTO = {'ano', 'regiao', 'ufNome', 'uf', 'municipio', 'ibge', 'escola', 'cod',
         'dep', 'loc', 'locDif', 'sit', 'latTxt', 'lonTxt'}

PROFS = ['profAdministrativo', 'profServicos', 'profBibliotecario', 'profSaude',
         'profCoordenador', 'profFonoaudiologo', 'profNutricionista', 'profPsicologo',
         'profAlimentacao', 'profPedagogo', 'profSecretario', 'profSeguranca',
         'profMonitor', 'profGestao', 'profAssistenteSocial', 'profLibras',
         'profAgricola', 'profBraille']
INTEIROS = {'salas', 'salasClimatizadas', 'salasAcessiveis', 'desktops',
            'notebooks', 'tablets'} | set(PROFS)

ACC_BRUTOS = ('accCorrimao', 'accElevador', 'accPisosTateis', 'accVaoLivre',
              'accRampas', 'accSinalTatil', 'accSinalVisual', 'accSinalizacao',
              'accInexistente')


# ----------------------------------------------------------------------
# UTILITÁRIOS
# ----------------------------------------------------------------------
def baixar_texto(url):
    req = urllib.request.Request(url, headers={"User-Agent": "escolas-quilombolas-bot/1.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read().decode("utf-8-sig")


def para_bin(v):
    if v == '1':
        return 1
    if v == '0':
        return 0
    return None


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

    # 2) inteiro corrompido: recolocamos o ponto decimal
    ref_alvo = (ref[0] if e_lat else ref[1]) if ref else None
    melhor, melhor_dist = None, None
    for k in ((1, 2) if e_lat else (2, 1)):
        if len(digitos) <= k:
            continue
        cand = int(digitos[:k]) + int(digitos[k:]) / (10 ** (len(digitos) - k))
        if neg:
            cand = -cand
        if not faixa_ok(cand):
            continue
        if ref_alvo is None:
            return cand
        dist = abs(cand - ref_alvo)
        if dist <= 1.5 and (melhor_dist is None or dist < melhor_dist):
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
    sem_geo = 0
    for r in registros:
        ref = por_codigo.get(r.get('ibge'))
        lat = recupera_coord(r.get('latTxt'), ref, True)
        lon = recupera_coord(r.get('lonTxt'), ref, False)
        if lat is not None and lon is not None:
            r['lat'], r['lon'], r['fonteGeo'] = round(lat, 6), round(lon, 6), 'escola'
        elif ref:
            r['lat'], r['lon'], r['fonteGeo'] = round(ref[0], 4), round(ref[1], 4), 'municipio'
        else:
            r['lat'], r['lon'], r['fonteGeo'] = None, None, 'nenhuma'
            sem_geo += 1
    print(f"Georreferenciamento: {sum(1 for r in registros if r['fonteGeo']=='escola')} pela própria coordenada, "
          f"{sum(1 for r in registros if r['fonteGeo']=='municipio')} por centróide municipal, {sem_geo} sem localização.")
    return sem_geo


# ----------------------------------------------------------------------
# LEITURA DA PLANILHA
# ----------------------------------------------------------------------
def baixa_escolas():
    print(f"Baixando planilha: {CSV_URL}")
    linhas = list(csv.reader(io.StringIO(baixar_texto(CSV_URL))))
    if not linhas:
        raise RuntimeError("Planilha vazia ou inacessível (confira se ela está publicada).")

    # localiza a linha do cabeçalho (tolera linhas de título acima dos dados)
    inicio = None
    for i, linha in enumerate(linhas[:10]):
        if 'NO_ENTIDADE' in [h.replace('\xa0', ' ').strip() for h in linha]:
            inicio = i
            break
    if inicio is None:
        raise RuntimeError("Não encontrei o cabeçalho da tabela de Escolas (falta a coluna "
                           "NO_ENTIDADE). Verifique se a aba publicada é a dos dados e se "
                           "os nomes das colunas estão na primeira linha.")

    cabecalho = [h.replace('\xa0', ' ').strip() for h in linhas[inicio]]
    indice, faltando = {}, []
    for coluna, campo in CAMPOS.items():
        if coluna in cabecalho:
            indice[campo] = cabecalho.index(coluna)
        else:
            faltando.append(coluna)
    if faltando:
        print("AVISO: colunas ausentes na planilha (campos ficarão 'sem dado'):")
        for c in faltando:
            print(f"  - {c}")

    # se a coluna de localização diferenciada existir, usamos para filtrar;
    # se não existir, assumimos que a planilha já é o recorte quilombola
    tem_loc_dif = indice.get('locDif') is not None

    registros, excluidas, duplicadas, vistos = [], 0, 0, set()
    for linha in linhas[inicio + 1:]:
        if not any(c.strip() for c in linha):
            continue

        def bruto(campo):
            i = indice.get(campo)
            if i is None or i >= len(linha):
                return ''
            return (linha[i] or '').replace('\xa0', '').strip()

        if bruto('escola') in ('', '*'):
            continue
        # mantém escolas em comunidade quilombola (3); linhas em branco ficam,
        # já que a planilha já é o recorte quilombola
        if SO_QUILOMBOLAS and tem_loc_dif and bruto('locDif') not in ('3', '', '*'):
            excluidas += 1
            continue
        cod = bruto('cod')
        if cod and cod in vistos:
            duplicadas += 1
            continue
        if cod:
            vistos.add(cod)

        r = {}
        for coluna, campo in CAMPOS.items():
            if campo in ('latTxt', 'lonTxt'):
                r[campo] = bruto(campo)
            elif campo in TEXTO:
                v = bruto(campo)
                r[campo] = v if v not in ('', '*') else None
            elif campo in INTEIROS:
                r[campo] = para_int(bruto(campo))
            else:
                r[campo] = para_bin(bruto(campo))

        # campos derivados
        recursos = [r.get(c) for c in ACC_BRUTOS if not c.endswith('INEXISTENTE')]
        if 1 in recursos:
            r['acess'] = 1
        elif r.get('accInexistente') == 1 or 0 in recursos:
            r['acess'] = 0
        else:
            r['acess'] = None
        profs = [r.get(c) for c in PROFS]
        r['profTotal'] = sum(p for p in profs if p) if any(p for p in profs) else None
        registros.append(r)

    print(f"{len(registros)} escolas lidas ({excluidas} fora do recorte quilombola, {duplicadas} duplicadas ignoradas).")
    ufs = {}
    for r in registros:
        ufs[r['uf']] = ufs.get(r['uf'], 0) + 1
    print("Por UF: " + ", ".join(f"{uf}={n}" for uf, n in sorted(ufs.items())))
    return registros


# ----------------------------------------------------------------------
# GERAÇÃO DO index.html
# ----------------------------------------------------------------------
def gera_pagina(registros, sem_geo):
    with open(TEMPLATE_PATH, encoding='utf-8') as f:
        tpl = f.read()

    municipios = len({r['ibge'] for r in registros if r['ibge']})
    ufs = len({r['uf'] for r in registros if r['uf']})
    anos = sorted({r['ano'] for r in registros if r['ano']})
    ano = anos[-1] if anos else '—'

    subs = {
        '__DATA_JSON__': json.dumps(registros, ensure_ascii=False),
        '__TOTAL_ESCOLAS__': f'{len(registros):,}'.replace(',', '.'),
        '__TOTAL_MUNICIPIOS__': f'{municipios:,}'.replace(',', '.'),
        '__TOTAL_UFS__': str(ufs),
        '__ANO_CENSO__': str(ano),
        '__NAO_GEOCODIFICADOS__': str(sem_geo),
        '__DATA_GERACAO__': datetime.now().strftime('%d/%m/%Y'),
        '__LINK_PLANILHA__': LINK_PLANILHA,
    }
    for k, v in subs.items():
        tpl = tpl.replace(k, v)

    restantes = re.findall(r'__[A-Z_]+__', tpl)
    if restantes:
        raise RuntimeError(f"Placeholders não substituídos: {restantes}")

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(tpl)
    print(f"{OUTPUT_PATH} gerado com {len(registros)} escolas.")


def main():
    registros = baixa_escolas()
    if len(registros) < MINIMO_REGISTROS:
        print(f"ERRO: só vieram {len(registros)} registros (mínimo esperado: {MINIMO_REGISTROS}). "
              f"Abortando sem sobrescrever {OUTPUT_PATH}. Se a planilha publicada é mesmo um recorte "
              f"menor, ajuste MINIMO_REGISTROS no topo do script.")
        sys.exit(1)

    por_codigo = carrega_municipios()
    sem_geo = geocodifica(registros, por_codigo)

    # remove campos de trabalho e de LGPD (não vão para o JSON público)
    for r in registros:
        for c in ('latTxt', 'lonTxt', 'endereco', 'bairro', 'ufNome') + ACC_BRUTOS:
            r.pop(c, None)

    gera_pagina(registros, sem_geo)


if __name__ == "__main__":
    main()
