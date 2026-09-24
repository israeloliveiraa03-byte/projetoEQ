# Escolas Quilombolas em Dados — CONAQ / Coletivo de Educação

Painel público sobre as escolas localizadas em comunidades quilombolas (microdados do Censo Escolar/INEP), com mapa em camadas, indicadores e cruzamento de variáveis. Atualização automática semanal.

## Estrutura

```
escolas-quilombolas-em-dados/
│   atualizar_dados.py
│   template.html
│   README.md
│   .gitignore
│   (index.html ← gerado pelo script, não editar à mão)
└── .github/
    └── workflows/
        └── atualizacao-semanal.yml
```

## Como funciona

1. O Coletivo mantém a planilha no Google Sheets (mesma estrutura da tabela "Escola" do Censo, com o recorte quilombola).
2. Toda segunda, uma GitHub Action roda `atualizar_dados.py`, que baixa a planilha em CSV, limpa, recupera as coordenadas e regenera o `index.html` a partir do `template.html`.
3. O script compara o resultado com o `index.html` já publicado. **Se nem os dados nem o template mudaram, o arquivo não é tocado e não há commit**; a data "Última atualização da base" só muda quando algo de fato mudou. Se mudou, o robô commita e o site (GitHub Pages ou Vercel) publica sozinho.

## Configuração única

1. **Crie a planilha:** no Google Sheets, cole os dados começando na célula A1 (mantenha a linha de cabeçalho com os nomes de coluna do Censo). Deixe apenas UMA aba com os dados.
2. **Compartilhe como público:** Compartilhar → "Qualquer pessoa com o link" pode visualizar.
3. **Pegue o `SHEET_ID` e o `GID` da URL:**

   ```
   https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit#gid=<GID>
   ```

4. Abra `atualizar_dados.py` e preencha `SHEET_ID`, `GID` e `LINK_PLANILHA` (ou, se preferir não editar o script, crie-os como *Variables* em Configurações → Segredos e variáveis → Actions e descomente o bloco `env:` do workflow).
5. Suba para o repositório: `atualizar_dados.py`, `template.html`, `README.md`, `.gitignore` e a pasta `.github/`.
6. Aba Actions → "Atualização semanal" → **Run workflow** para testar. (O workflow já declara a permissão de escrita; só se a organização bloquear, marque Configurações → Ações → Permissões de fluxo de trabalho → "Leitura e escrita".)

## Testar no seu computador

Precisa apenas de Python 3.9 ou mais novo (nada para instalar).

```
python3 atualizar_dados.py                    # baixa a planilha configurada
python3 atualizar_dados.py --csv escolas.csv  # usa um CSV local (a planilha não precisa estar pública)
MINIMO_REGISTROS=1 python3 atualizar_dados.py --csv amostra.csv   # amostra pequena, só para ver o painel
```

Depois abra o `index.html` no navegador. O terminal mostra o resumo: escolas lidas, por UF, quantas foram posicionadas pela própria coordenada e quantas pelo centróide do município.

## Ajustes

Ficam no topo de `atualizar_dados.py`:

| O que ajustar | Onde |
|---|---|
| Coluna renomeada na planilha/INEP | Dicionário `CAMPOS`. O log avisa "colunas ausentes" e sugere a parecida (ex.: `IN_MATERIAL_PED_QUILOMBOLA → IN_MATERIAL_ESP_QUILOMBOLA`). Revise esse aviso na primeira execução real. |
| Quais códigos entram como "quilombola" | `CODIGOS_QUILOMBOLAS` (padrão `{3}`). Confira no dicionário do INEP do ano se outros códigos de `TP_LOCALIZACAO_DIFERENCIADA` também identificam quilombos. |
| Recorte menor (ex.: um estado) | `MINIMO_REGISTROS` (padrão 200) |
| Queda máxima aceita no total de escolas | `QUEDA_MAXIMA` (padrão 30%) |
| Distância máxima entre a coordenada e o município | `TOLERANCIA_GRAUS` (padrão 3°) |
| Dia/hora da atualização | linha `- cron:` do workflow (sempre em UTC) |

## Como os dados são tratados

- **Recorte:** só escolas com `TP_LOCALIZACAO_DIFERENCIADA` em `CODIGOS_QUILOMBOLAS`.
- **Linhas repetidas:** se a mesma escola (`CO_ENTIDADE`) aparece mais de uma vez, fica a linha do Censo mais recente.
- **Sem dado:** campos vazios, `*` e códigos "não informado" viram *sem dado* e ficam fora do denominador dos percentuais.
- **Coordenadas:** quando a planilha entrega o número corrompido (`-2,491,758,333`), o script recoloca a vírgula testando as possibilidades e escolhendo a mais próxima do centróide do município (código IBGE). Coordenadas a mais de `TOLERANCIA_GRAUS` do município são descartadas. Sem coordenada válida, a escola vai para o centróide do município e aparece no mapa com marcador tracejado ("posição aproximada").
- **Acessibilidade (algum recurso):** vale 1 se a escola declara ao menos um recurso; 0 se declara só "inexistente" ou todos zerados.
- **Profissionais (total):** soma das categorias `QT_PROF_*` (profissionais escolares não docentes).
- **Privacidade:** endereço e bairro são lidos, mas **não vão para o JSON público** do painel.
- **Downloads:** "Base completa em CSV" traz todas as colunas com os nomes e códigos do INEP; "Seleção atual (CSV)" é uma tabela resumida com rótulos legíveis.

## Travas de segurança

O script aborta **sem sobrescrever o painel publicado** quando:

- a planilha vem vazia, não é a tabela "Escola" ou o Google devolve uma página HTML (planilha não pública / GID errado);
- vêm menos que `MINIMO_REGISTROS` escolas;
- o total cai mais que `QUEDA_MAXIMA` em relação ao painel publicado (use `--forcar` se a queda for legítima).

## Problemas comuns

- **A Action falhou com "página HTML em vez do CSV":** confira o compartilhamento da planilha e o `GID`.
- **Workflow parou de rodar sozinho:** em repositórios públicos, o GitHub desativa agendamentos após 60 dias sem atividade no repositório. Como o Censo muda pouco, isso pode acontecer. Se acontecer, abra Actions → "Atualização semanal" → **Enable workflow**.
- **O robô não consegue dar push:** veja o passo 6 da configuração (permissão de escrita).
- **Indicador aparece como "sem dado" para todas as escolas:** provável coluna renomeada; veja o aviso "colunas ausentes" no log.
