# Escolas Quilombolas em Dados — CONAQ / Coletivo de Educação

Painel público sobre as escolas localizadas em comunidades quilombolas (microdados do Censo Escolar/INEP), com mapa em camadas, indicadores e cruzamento de variáveis. Atualização automática semanal.

## Estrutura

```
escolas-quilombolas-em-dados/
│   atualizar_dados.py
│   template.html
│   README.md
│   (index.html ← gerado pelo script, não criar à mão)
└── .github/
    └── workflows/
        └── atualizacao-semanal.yml
```

## Como funciona

1. O Coletivo mantém a planilha no Google Sheets (mesma estrutura da tabela "Escola" do Censo, com o recorte quilombola).
2. Toda segunda, uma GitHub Action roda `atualizar_dados.py`, que baixa a planilha em CSV, limpa, recupera as coordenadas e regenera o `index.html`.
3. Se a planilha mudou, o robô commita e o site (GitHub Pages ou Vercel) publica sozinho. Se não mudou, nada é commitado.

## Configuração única

1. **Crie a planilha:** no Google Sheets, cole os dados começando na célula A1 (mantenha a linha de cabeçalho com os nomes de coluna do Censo). Deixe apenas UMA aba com os dados.
2. **Compartilhe como público:** Compartilhar → "Qualquer pessoa com o link" pode visualizar.
3. **Pegue o `SHEET_ID` e o `GID` da URL:**

   ```
   https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit#gid=<GID>
   ```

4. Abra `atualizar_dados.py` e preencha `SHEET_ID`, `GID` e `LINK_PLANILHA`.
5. Coloque `atualizar_dados.py`, `template.html` e o workflow no repositório.
6. No GitHub: Configurações → Ações → permissões gerais de fluxo de trabalho → marque "Permissões de leitura e escrita".
7. Aba Actions → "Atualização semanal" → **Run workflow** para testar.

## Ajustes

- **Coluna renomeada na planilha?** O script avisa no log ("colunas ausentes"); corrija o nome no dicionário `CAMPOS`.
- **Recorte menor (só um estado)?** Ajuste `MINIMO_REGISTROS`.
- **Trocar o dia/hora:** linha `- cron:` no workflow (sempre em UTC).

## Segurança

Se a planilha vier vazia/cortada (erro de rede, permissão), o script aborta e não sobrescreve o painel publicado.
