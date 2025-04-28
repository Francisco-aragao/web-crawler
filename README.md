# web-crawler

Trabalho desenvolvido para a disciplina de Recuperação de Informação.

Francisco Teixeira Rocha Aragão - 2021031726

# Requisitos

1 - Crawler apenas coleta páginas no formato HTML. 
2 - Crawler não revisita páginas já visitadas.
3 - Código paralelizado com o uso de threads.
4 - Crawler respeita o arquivo robots.txt durante a coleta
5 - Crawler salva o conteúdo das páginas coletadas em arquivos WARC.

Obs: Todos esses requisitos estão mostrados no código com os respectivos comentários:
    - SELECTION POLICY
    - REVISITATION POLICY
    - PARALLELIZATION POLICY
    - POLITENESS POLICY
    - STORAGE POLICY

# Execução

Para executar o crawler, utilize o seguinte comando:

```bash
python3 main.py -s <seeds> -n <limite>
```

Onde:
- `<seeds>`: URL(s) de semente para iniciar a coleta salvas em um arquivo.
- `<limite>`: Número máximo de páginas a serem coletadas.

Os arquivos do corpus serão salvos na pasta `corpus/` com o nome `corpus_<idx>.warc` e compactados em `.gz`. <idx> é o índice do arquivo, começando em 0, separados em blocos de 1000 páginas.

### Flags adicionais

- `-d`: Ativa o modo de depuração, exibindo informações de coleta.
- `-c`: Modo de debug do código, exibindo informações de execução.
- `-sr`: Salva arquivos .json com estatísticas da coleta executada.
    - Os arquivos serão salvos na raiz do projeto com os nomes:
        - `time_per_block_THREADS_<num>.json`= tempo médio por bloco de páginas coletadas.
        - `domain_count.json` = contagem de páginas coletadas por domínio.
        - `visited_urls.json` = lista de URLs visitadas.
        - `tokens_by_page.json` = contagem de tokens por página.
