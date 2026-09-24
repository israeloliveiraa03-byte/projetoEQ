# Escolas Quilombolas em Dados — CONAQ / Coletivo de Educação

Painel público sobre as escolas localizadas em comunidades quilombolas, a partir dos microdados do Censo Escolar (INEP): mapa, indicadores de infraestrutura, oferta de EJA, comparação com os demais territórios diferenciados e análise de correlação.

O painel é um **arquivo HTML único**, gerado a mão quando sai um Censo novo. Sem servidor, sem banco de dados, sem automação.

## Estrutura

```
escolas-quilombolas-em-dados/
    atualizar_dados.py     ← o gerador
    template.html          ← o painel, com marcadores no lugar dos dados
    README.md
    .gitignore
    index.html             ← gerado pelo script; é o que se publica
    municipios-ibge.csv    ← baixado na primeira execução, fica de cache
```

## Como gerar o painel

**1. Baixe os microdados** em [gov.br/inep → microdados do Censo Escolar](https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar). Dentro do ZIP, em `dados/`, você precisa de duas tabelas:

- `Tabela_Escola_AAAA.csv` — obrigatória
- `Tabela_Turma_AAAA.csv` — opcional, mas é ela que traz o EJA

> **Atenção à versão da tabela de Escola.** Existem duas: a completa (`Tabela_Escola_AAAA.csv`, 302 colunas) e a anonimizada (`Tabela_Escola_AAAA_V2.csv`, 290 colunas). Só a **completa** traz `LATITUDE` e `LONGITUDE` (colunas AH e AI). Com a `_V2`, o painel funciona igual, mas o mapa agrupa todas as escolas por município. Use a completa se quiser o mapa detalhado.

**2. Rode o script**, com os dois CSVs na mesma pasta que ele:

```
python3 atualizar_dados.py --escola Tabela_Escola_2025.csv --turma Tabela_Turma_2025.csv
```

**3. Abra o `index.html`** no navegador para conferir e publique-o (GitHub Pages, Vercel, ou qualquer lugar que sirva um arquivo estático).

Precisa apenas de Python 3.9 ou mais novo — nada para instalar. A primeira execução baixa a lista de municípios do IBGE e guarda como `municipios-ibge.csv`; a partir daí o script roda sem internet.

### Outras opções

| Opção | Para quê |
|---|---|
| `--saida painel.html` | gerar com outro nome, sem sobrescrever o publicado |
| `--so-quilombolas` | carregar só o código 3 (painel menor, sem comparação entre tipos) |
| `--coordenadas arquivo.csv` | usar coordenadas de outra fonte, no lugar das da tabela (veja abaixo) |

## Como o mapa lida com a localização

A tabela completa de Escola traz `LATITUDE` e `LONGITUDE` (colunas AH e AI), mas **nem toda escola declara**, e a cobertura varia muito entre os territórios:

| Território | Com coordenada própria | Cobertura |
|---|---|---|
| Assentamento | 3.579 de 4.519 | 79,2% |
| Quilombola | 2.075 de 2.737 | 75,8% |
| Outros povos tradicionais | 863 de 1.503 | 57,4% |
| Terra indígena | 1.851 de 3.713 | 49,9% |
| **Total** | **8.368 de 12.472** | **67,1%** |

O mapa é híbrido, e mostra isso na legenda:

- **Ponto** — escola na coordenada que declarou.
- **Círculo** — as escolas sem coordenada do município, agrupadas. O raio cresce pela raiz quadrada da contagem (é assim que a área acompanha o número de escolas, que é como o olho compara símbolos); há um piso de 4px para o círculo de uma escola só não sumir.

Agrupar as que não têm coordenada não é enfeite. Se cada uma virasse um ponto no centróide, todas as escolas de um município cairiam **exatamente no mesmo pixel** — em Itapecuru Mirim (MA) seriam 41 num ponto só, e o mapa pareceria mais vazio do que é.

### Como as coordenadas são validadas

Cada coordenada é conferida contra o **envelope da própria UF**, calculado a partir dos centróides dos municípios daquela UF mais uma margem. Uma escola da Bahia com coordenada em Roraima é descartada e cai no círculo do município.

Aferir pela distância ao centróide do *município* seria mais preciso em tese, mas dá errado na prática, por dois motivos:

1. **Municípios amazônicos são enormes.** Altamira (PA) tem 159 mil km². Escolas indígenas legítimas do sul do município ficam a 600 km do centróide.
2. **A lista de centróides tem erros.** Pau d'Arco (PA) aparece na referência a 750 km do lugar certo — o município fica a 07°49'S, 50°02'W, no sul do Pará, e não no nordeste. As coordenadas que o INEP registra para as escolas Kayapó de lá estão certas; o centróide é que está errado.

Uma versão anterior deste script descartava essas 13 escolas como "suspeitas". Agora elas entram.

Dentro dessa validação, o script ainda reconstrói coordenadas que chegaram como inteiro, quando uma planilha leu o ponto decimal como separador de milhar (`-2.491758333` virando `-2491758333`). Aí sim o centróide do município é usado, mas só para escolher entre os candidatos possíveis.

### Coordenadas de outra fonte

Se você tiver um arquivo melhor — o [Catálogo de Escolas do INEP](https://censobasico.inep.gov.br/censobasico/#/), por exemplo, ou um levantamento do próprio coletivo:

```
python3 atualizar_dados.py --escola Tabela_Escola_2025.csv \
                           --turma Tabela_Turma_2025.csv \
                           --coordenadas minhas-coordenadas.csv
```

Ele precisa de uma coluna de código INEP, uma de latitude e uma de longitude — o script acha sozinho, aceitando variações de nome. Esse arquivo tem **prioridade** sobre a coluna da tabela: quem o passou quis corrigir alguma coisa.

### Endereço e telefone

A tabela completa também traz `DS_ENDERECO`, `NU_ENDERECO`, `DS_COMPLEMENTO`, `NO_BAIRRO`, `CO_CEP`, `NU_DDD` e `NU_TELEFONE`. O painel é uma página pública, e este projeto optou por não republicar esses campos — eles nem chegam a ser lidos. Para um painel interno do coletivo (uma lista de contatos das escolas, por exemplo), acrescente-os a `CAMPOS_ESCOLA` no script.

## O que o painel mostra

| Seção | O que responde |
|---|---|
| Mapa | Onde estão as escolas: ponto quando há coordenada, círculo por município quando não há |
| Infraestrutura | % de escolas do recorte com cada serviço ou dependência |
| Comparação entre tipos | Como a escola quilombola se compara à indígena, à de assentamento e às de outros povos tradicionais |
| EJA | Turmas de EJA efetivamente abertas, por etapa, turno e tipo de território |
| Correlação | Duas variáveis ao mesmo tempo, com reta de tendência, r de Pearson e R² |
| Tabela | Relação das escolas, ordenável, com download da seleção |
| Cruzador | Tabela cruzada de qualquer par de dimensões |

Os botões de download estão em dois lugares: na seção **Relação das escolas** (a seleção filtrada, em CSV ou JSON) e na seção **Fontes** (a base completa, com os nomes de coluna do INEP).

## As duas tabelas do Censo

O painel cruza as duas pelo código da escola (`CO_ENTIDADE`):

- **Tabela de Escola** — infraestrutura, dependência, localização, e a declaração de que a escola oferece EJA (`IN_EJA`, sim/não).
- **Tabela de Turma** — quantas turmas de EJA foram efetivamente abertas (`QT_TUR_EJA*`), por etapa e turno.

A segunda é o que dá o tamanho real da oferta: a de Escola só diz que a modalidade existe, não quantas turmas. Sem `--turma`, o painel funciona e a seção de EJA fica vazia.

## Universo carregado

O painel carrega as escolas em área de localização diferenciada (`TP_LOCALIZACAO_DIFERENCIADA`), não só as quilombolas:

| Código | Tipo | Escolas (Censo 2025) |
|---|---|---|
| 3 | Comunidade quilombola | 2.737 |
| 2 | Terra indígena | 3.713 |
| 1 | Área de assentamento | 4.519 |
| 8 | Outros povos e comunidades tradicionais | 1.503 |

Carregar os quatro é o que permite comparar. O filtro do painel **abre no recorte quilombola**; as seções de comparação e correlação usam os quatro de propósito, e dizem isso na tela.

## Por que os dados ficam dentro do HTML

O `index.html` é um arquivo único, sem `dados.json` ao lado. Isso é deliberado: o Chrome bloqueia `fetch()` em páginas abertas por `file://`, então um painel dividido em dois arquivos pararia de funcionar por duplo clique — e mandar o arquivo por e-mail, pen drive ou WhatsApp para alguém do coletivo é um dos usos.

Para o arquivo único não ficar impraticável, os dados vão em **formato colunar**: um array por campo, em vez de um objeto por escola. Com 12.472 escolas e 123 campos:

| Formato | Arquivo | Servido (gzip) |
|---|---|---|
| Um objeto por escola | 24,7 MB | 922 KB |
| Colunar simples | 4,3 MB | 407 KB |
| **Colunar como está no script** | **3,0 MB** | **392 KB** |

O ganho vem de não repetir o nome de cada campo 12.472 vezes, de guardar os 70 campos sim/não como uma string de um caractere por escola, e de trocar texto repetido (região, UF, município) por dicionário + índices. O painel remonta as linhas ao abrir, em cerca de 1 segundo.

## Ajustes

Ficam no topo de `atualizar_dados.py`:

| O que ajustar | Onde |
|---|---|
| Coluna renomeada pelo INEP | Dicionários `CAMPOS_ESCOLA` / `CAMPOS_TURMA`. O log avisa "colunas ausentes" e sugere a parecida. |
| Quais territórios entram | `UNIVERSO` (padrão: os quatro tipos) |
| Mínimo de escolas aceito | `MINIMO_REGISTROS` (padrão 200) |
| Margem do envelope da UF na validação de coordenadas | `MARGEM_UF` (padrão 2°) |

Mudanças de texto, cores e seções ficam no `template.html`. **Nunca edite o `index.html` à mão** — ele é sobrescrito na próxima geração.

## Correção importante: etapas de ensino

Versões anteriores deste painel mostravam as "etapas ofertadas" a partir dos campos `IN_COMUM_*` da tabela de Escola. **Isso estava errado.** No dicionário do INEP, esses campos significam:

> "Escola oferece matrículas de alunos com deficiência, transtorno do espectro autista (TEA), altas habilidades ou superdotação em Classes Comuns — [etapa]"

Ou seja: eles dizem em que etapa há aluno da educação especial, não que etapa a escola oferece. Formam um par com `IN_ESP_EXCLUSIVA_*` (classe especial exclusiva) e são todo o bloco de educação especial do Censo, das variáveis 347 a 370.

O painel agora deriva as etapas da **tabela de Turma**: a etapa conta como ofertada quando a escola abriu ao menos uma turma dela. A diferença é grande — no recorte quilombola de 2025:

| Etapa | Painel antigo dizia | Turmas abertas |
|---|---|---|
| Creche | 1.525 | 741 |
| Pré-escola | 2.083 | 1.697 |
| Fund. anos iniciais | 2.213 | 1.443 |
| Fund. anos finais | 837 | 1.781 |
| Ensino médio | 132 | 161 |
| EJA fundamental | 849 | 697 |

Os campos de educação especial continuam no painel, agora com o rótulo certo ("Aluno com deficiência em classe comum – [etapa]") — são um indicador legítimo de inclusão, só não são o que estavam dizendo ser.

### Turma multisseriada

**69% das escolas quilombolas com ensino fundamental juntam séries diferentes numa mesma turma.** Quando isso acontece, o Censo costuma lançar a turma inteira nos anos finais, então uma escola que ensina do 1º ao 9º ano pode aparecer com zero turmas de anos iniciais.

Por isso o painel marca essas escolas com o chip **multisseriada** em vez de fingir que a divisão anos iniciais / anos finais é exata. O campo também está disponível como indicador, para filtro e cruzamento — é um dado central para a educação escolar quilombola.

## Como os dados são tratados

- **Recorte:** escolas com `TP_LOCALIZACAO_DIFERENCIADA` em `UNIVERSO`.
- **Linhas repetidas:** se a mesma escola (`CO_ENTIDADE`) aparece mais de uma vez, fica a do Censo mais recente.
- **Sem dado:** campos vazios, `*` e códigos "não informado" (≥ 88888) viram *sem dado* e ficam fora do denominador dos percentuais — por isso o "n" varia entre indicadores.
- **Acessibilidade (algum recurso):** vale 1 se a escola declara ao menos um recurso; 0 se declara só "inexistente" ou todos zerados.
- **Profissionais (total):** soma das categorias `QT_PROF_*` — profissionais escolares **não docentes**. Professores não entram nessa contagem.
- **Etapas ofertadas:** derivadas da tabela de Turma (ao menos uma turma aberta na etapa). Veja a correção acima.
- **Turmas de EJA:** somas da tabela de Turma. As etapas (fundamental anos iniciais, anos finais, médio) **não** somam o total: cursos FIC e técnicos integrados à EJA entram no total e não nessas etapas — em 2025, 300 das 2.100 turmas quilombolas. Já os recortes de turno (noturno, diurno, EAD) somam o total exatamente, mas são as mesmas turmas vistas de outro ângulo e não devem ser somados às etapas.
- **Coordenadas:** vêm das colunas `LATITUDE`/`LONGITUDE` da tabela completa de Escola e são validadas contra o envelope da UF; as escolas sem coordenada entram no círculo do município. Veja a seção sobre o mapa, acima.
- **Privacidade:** endereço, CEP e telefone existem na tabela completa, mas não são lidos nem republicados.

## Como ler a correlação

Cada ponto pode ser um município, uma UF ou uma escola. A reta é a regressão linear por mínimos quadrados; `r` é o coeficiente de Pearson e `R²` diz quanto da variação de Y a reta explica.

- **Variáveis sim/não** (internet, EJA, biblioteca) só fazem sentido agregadas: quando o ponto é município ou UF, elas viram *% de escolas com o item*. Na unidade "uma escola" elas valem 0 ou 1 e os pontos se empilham em duas linhas — a reta fica pouco informativa.
- **O mínimo de escolas por ponto** evita que um município com duas escolas (onde o percentual só pode ser 0%, 50% ou 100%) desloque a reta.
- **Correlação não é causa.** Duas variáveis podem subir juntas por efeito de uma terceira — o porte do município, tipicamente.
- Cuidado com pares quase tautológicos: "turmas de EJA" × "turmas de EJA no noturno" dá r = 0,996 porque quase toda turma de EJA é noturna, o que não é um achado sobre duas coisas diferentes.

## Travas de segurança

O script para **sem gerar nada** quando:

- o arquivo não existe, está vazio, ou não é a tabela esperada (faltam colunas essenciais);
- vêm menos que `MINIMO_REGISTROS` escolas — sinal de CSV truncado ou tabela errada;
- nenhuma escola casa com a tabela de Turma — sinal de que as duas são de anos diferentes;
- sobrou algum marcador não substituído no template.

Como o `index.html` só é escrito no fim, uma falha no meio do caminho nunca deixa o painel publicado pela metade.

## Problemas comuns

- **"faltam as colunas [...]":** o arquivo não é a tabela certa, ou foi aberto e salvo por um editor que mexeu no cabeçalho. Use o CSV como veio do INEP.
- **"nenhuma escola casou com a tabela de Turma":** as duas tabelas são de anos diferentes.
- **"não foi possível baixar os centróides municipais":** sem internet na primeira execução. Baixe o CSV à mão pelo endereço que o erro mostra e salve como `municipios-ibge.csv` na pasta do script.
- **Indicador "sem dado" para todas as escolas:** provável coluna renomeada pelo INEP; veja o aviso "colunas ausentes" no log.
- **Página em branco com aviso de bibliotecas:** o painel carrega Leaflet e Chart.js de CDN e precisa de internet na primeira abertura.
