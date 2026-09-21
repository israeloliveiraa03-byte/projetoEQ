Escolas Quilombolas em Dados — CONAQ / Coletivo de Educação
Painel público sobre as escolas localizadas em comunidades quilombolas(microdados do Censo Escolar/INEP), com mapa em camadas, indicadores de infraestrutura e cruzamento de variáveis. Atualização automática semanal.

Como funciona
O Coletivo mantém a planilha no Google Sheets (mesma estrutura da tabela"Escola" do Censo, com o recorte quilombola), publicada para a web.
Toda segunda, uma GitHub Action roda , que baixa aplanilha em CSV, limpa os dados, recupera as coordenadas e regenera o.atualizar_dados.pyindex.html
Se a planilha mudou, o robô commita e o site (GitHub Pages ou Vercel)publica sozinho. Se não mudou, nada é commitado.
A planilha já está configurada
O link da planilha publicada já está embutido no (constantes e ). Se um dia a planilha mudar deendereço, basta substituir essas duas linhas no topo do script.atualizar_dados.pyCSV_URLLINK_PLANILHA

Importante: no Google Sheets, em "Arquivo → Compartilhar → Publicarna web", mantenha marcada a opção "Republicar automaticamente quandohouver alterações". Sem isso, o link CSV continua servindo a versãoantiga mesmo depois de a instituição atualizar a planilha.

Testar na sua máquina
python3 atualizar_dados.py
Isso gera o . Dê dois cliques nele para abrir no navegador econferir o painel com os dados atuais.index.html

Colocar no ar (GitHub)
Crie um repositório e suba esta pasta completa (mantendo o caminho)..github/workflows/atualizacao-semanal.yml
Sem GitHub: Configurações → Ações → permissões gerais de fluxo de trabalho → →marque "Permissões de leitura e escrita".
Aba Actions → "Atualização semanal" → Run workflow para testar.
Publique via GitHub Pages (Configurações → Pages, branch main) ou Vercel.
Se algo mudar na planilha
Se uma coluna for renomeada, o script avisa no log ("colunas ausentes")em vez de quebrar; ajuste o nome no dicionário, no topo do.CAMPOSatualizar_dados.py

Segurança
Se a planilha vier vazia ou cortada (erro de rede, permissão etc.), oscript aborta e não sobrescreve o painel publicado — ele só publicaquando confirma ter recebido um volume de registros consistente (mínimodefinido em ).MINIMO_REGISTROS

Estrutura da massa
escolas-quilombolas-em-dados/├── atualizar_dados.py                  # script de atualização├── template.html                       # painel (base para gerar o index.html)├── index.html                          # gerado pelo script (não editar à mão)└── .github/workflows/atualizacao-semanal.yml
