# Servidor de assinatura próprio: candidatos investigados

Data da pesquisa: 06/11/2026. Fonte: leitura de páginas públicas. **Nada abaixo foi executado ou testado por mim**: não tenho acesso à internet no ambiente de execução. "Afirma" significa "o README diz", não "funciona".

## Contexto

- As bibliotecas (Node, Python, PHP, Go) precisam de uma URL de conexão assinada. O algoritmo de assinatura fica em código ofuscado do TikTok e muda com frequência; por isso delegam a etapa a um servidor de assinatura, por padrão o Euler Stream.
- A documentação do TikTokLive afirma que todas as bibliotecas aceitam um servidor de assinatura **próprio** e que o do Euler Stream não é código aberto ([wiki: All About Signatures](https://github.com/isaackogan/TikTokLive/wiki/All-About-Signatures)).
- Na biblioteca Python, o endereço é o parâmetro `tiktok_sign_url` de `WebDefaults` ([PyPI](https://pypi.org/project/TikTokLive/)). Na Node, `SignConfig.basePath` ([repositório](https://github.com/zerodytrash/TikTok-Live-Connector)).

## Candidatos

| # | Candidato | O que afirma | Custo | Pontos de atenção |
|---|---|---|---|---|
| 1 | `tiktok-signer` (Rust) | Transporte TikTok LIVE auto-hospedado, sem navegador, que executa o bundle de assinatura do TikTok em ambiente sintético (QuickJS ou V8). Expõe `GET /webcast/fetch` e `/healthz`. Afirma funcionar com o `tiktok-live-connector` (Node) apontando para o servidor local ([repositório](https://github.com/nglmercer/tiktok-signer)). | Gratuito (código aberto, licença não verificada) | **Encontrei repositórios com descrição idêntica em contas diferentes** ([nglmercer](https://github.com/nglmercer/tiktok-signer), [moiseivasilev5-collab](https://github.com/moiseivasilev5-collab/tiktok-signer), [hernan-lc](https://github.com/hernan-lc/tiktok-signer)). Não sei qual é o original; pode haver cópia maliciosa. Exige Rust. Compatibilidade com a biblioteca **Python** não confirmada (o README cita a Node). |
| 2 | Assinador com Chromium headless (Playwright) | Mantém um Chromium numa página do TikTok e deixa o próprio script da página assinar a requisição. Um projeto de terceiros descreve essa abordagem ([PR #7](https://github.com/mariajunqueiramirandas-cpu/tik-live/pull/7)). | Gratuito, mas consome RAM/CPU (um navegador por instância) | Descrição vinda de um único PR; não verificada. Pode ser construída por nós como módulo, com manutenção contínua. |
| 3 | Código-fonte comercial de assinatura (EterZ) | Oferece o código completo para auto-hospedar, com "atualizações vitalícias" ([repositório](https://github.com/EterZ-byte/tiktok-signature-api)). | **Pago** ("entre em contato") | Fora do critério "sem serviço pago". |
| 4 | SDK de assinatura via RapidAPI | API hospedada de assinatura ([repositório](https://github.com/aloneangel45/tiktok-verifyfp-webcast-sdk)). | Chave de API de terceiro; camada gratuita não verificada | Dependência externa; fora do critério. |
| 5 | Euler Stream | Padrão das bibliotecas; plano gratuito e planos pagos. | Gratuito limitado; pago acima | Um porte relata cerca de 10 conexões por dia sem chave em IP compartilhado ([PHP](https://packagist.org/packages/nargor/tiktok-live-connector-php)). Não é requisito; serve como linha de base (T1). |

## Recomendação para o teste

1. **T1 (agora):** linha de base com o padrão da biblioteca, sem chave. Mostra se o fluxo gratuito funciona e quais são os limites reais.
2. **T2 (depois de revisarmos juntos):** apontar `--sign-url` para um servidor próprio. Antes de executar qualquer binário de terceiros, vou analisar o código-fonte com você; **não execute o candidato 1 antes disso**, por causa das cópias com a mesma descrição.
3. Se o T2 mostrar que a biblioteca Python não é compatível com o servidor do candidato 1, o caminho é um provador em Node (a biblioteca que o README cita) ou construir o assinador (candidato 2).
4. Nenhum candidato será adotado como dependência sem teste real e sem revisão do código.

## Pergunta em aberto

Não confirmei se algum destes servidores está **atualizado frente às mudanças atuais do TikTok**. Só o teste em live real responde.

## Revisão estática do `tiktok-signer` (nglmercer), 06/11/2026

Escopo: leitura do README e do `Cargo.toml` raiz pelo GitHub. **Nada foi executado, compilado nem baixado.** O código das crates não foi lido.

Observado:
- Repositório não é fork, 24 commits, 1 estrela, 0 forks, licença MIT declarada no `Cargo.toml`.
- O README desta cópia descreve outra arquitetura (um WebView da biblioteca Wry roda a página do TikTok e repassa os frames do WebSocket) da que li antes em outra cópia (assinatura headless com QuickJS/V8). **As cópias divergem**; a origem continua indefinida.
- O README documenta a crate `ttl-sign-webview`, mas o `Cargo.toml` raiz lista 16 crates e nenhuma tem esse nome. README e manifesto são inconsistentes.
- Dependências raiz são comuns (tokio, axum, reqwest com rustls, serde, prost, sha2). `protoc-bin-vendored` traz binário pré-compilado do protoc no build. As dependências de cada crate não foram vistas.
- Por projeto, o software opera um navegador real, injeta JavaScript (`bridge.js`) na página do TikTok, trata captcha entregando-o a uma pessoa e troca de "identidade de convidado" para escapar de bloqueios. Isso aumenta o risco de termos de uso e de manutenção.
- Todas as afirmações de "verificado em 2026-08-10" são do autor; não foram reproduzidas.

Situação: **NÃO APROVADO para execução.** Pendências: ler `build.rs`, `bridge.js`, `Dockerfile`, `docker-entrypoint.sh` e os `Cargo.toml` das crates; comparar as três cópias; rodar `cargo audit`/`cargo deny` (indisponíveis aqui: sem internet nem Rust); executar só em máquina virtual isolada e monitorar conexões de rede; confirmar suporte a Windows (o README que li trata de Linux/WebKitGTK).
