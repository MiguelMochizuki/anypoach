# AnyPoach: inspetor de página na extensão do Chrome

Data: 2026-11-21. Estado: aguardando aprovação do usuário. Continua a extensão da v0.2a (`docs/superpowers/plans/2026-11-21-anypoach-v020-chrome-companion.md`) e o item de fidelidade de `docs/superpowers/poach-parity.md`.

## Intenção e motivo

Quem usa a extensão quer recriar um componente web no tamanho e no estilo certos. Hoje a extensão mede só o elemento escolhido (a raiz): rect, estilos, texto e as animações que passam por ele ou por seus descendentes. Os descendentes que não animam não têm estilos no brief. Isso foi medido num teste real: ao gravar a seção "stages" de uma página, o brief trouxe a seção (1468×720, Inter 16/24) e o crossfade de opacidade, mas nada sobre o título, os cards e as tags, e o mock do front só pôde ser feito olhando o vídeo.

O usuário pediu "inspecionar a página completa e analisar em tempo real os componentes", com o visual do Poach original. Aqui isso quer dizer duas coisas: (1) passar o mouse em qualquer elemento da página e ver na hora os valores dele; (2) ao fixar um componente, o brief passar a conter a estrutura medida dos filhos dele.

## Metas, não metas e antimetas

Metas:
- Um cartão sobre a própria página que mostra, ao vivo, os valores do elemento sob o mouse.
- O brief ganha `evidence.browserEvidence.components`: os descendentes visíveis do componente fixado, com rect, estilos e texto curto.
- O assistente usa esses valores em vez de medir o vídeo (o prompt e a descrição das tools já dizem isso; passam a citar os componentes).
- Visual do cartão no estilo do Poach: fundo #FAFAF8, contorno #D8D8D3, tinta #292927, azul cobalto #2025C8 no realce, cápsulas de cor com o hex embaixo, botão escuro de largura total.

Não metas (ficam para depois):
- Painel lateral do Chrome com a árvore da página inteira (opção B da conversa). Reaproveitará as mesmas medições.
- Lista de componentes dentro da janela do AnyPoach (opção C).
- Medir `iframe` de outra origem, shadow DOM fechado, conteúdo de `canvas` ou `video`.
- Publicar na Chrome Web Store.

Antimetas (o que seria um fracasso mesmo que funcionasse):
- O cartão do inspetor aparecer dentro do vídeo gravado.
- Enviar ao AnyPoach, ou guardar, valores de elementos que o usuário só passou o mouse e não fixou.
- Texto de campos de formulário ou de elementos ocultos entrar no brief.
- O brief passar de 256 KiB e a sessão inteira ser recusada.

## Fatos verificados no código

- `capture.js` já tem a fase `selecting`: um contorno azul (`#2378ff`) segue o `pointermove`, `↑` sobe ao pai, clique ou Enter confirma, Esc cancela. Confirmar chama `start(elemento)`, que começa a sessão, amostra a cada 100 ms e envia um instantâneo a cada 1 s.
- `styles()` mede 17 propriedades de um elemento; `rect()` dá o retângulo na viewport; `visibleText()` já exclui campos de formulário, `[hidden]` e `aria-hidden`.
- As animações já são coletadas na árvore do elemento raiz (`getAnimations({ subtree: true })`), até 16 por sessão.
- O servidor valida cada sessão com modelos estritos (`bridge/evidence.py`) e limita o corpo a 256 KiB; o MCP lê `browserEvidence` com modelos `extra="ignore"` em `mcp/server.py`.
- Como a seleção termina ao fixar, o cartão só existe antes da sessão; depois dela, só o contorno some e a amostragem continua. Se alguém gravar a tela ainda escolhendo, o cartão aparece no vídeo (o banner atual já tem essa limitação).

## Abordagens consideradas

Onde o inspetor aparece:
- **A. Cartão sobre a página.** Escolhida. Os valores ficam ao lado do que se olha, e não pede permissão nova porque o `capture.js` já roda na página.
- **B. Painel lateral do Chrome.** Mostra a árvore inteira, mas exige a permissão `sidePanel` e muda o aviso de instalação. Fica para depois.
- **C. Dentro da janela do AnyPoach.** Afasta a informação do que se olha e some ao gravar. Descartada por ora.

Como os filhos entram no brief:
- **1. O usuário fixa cada componente.** Dados limpos, mas dá trabalho.
- **2. Fixa um e a extensão mede os descendentes.** Escolhida pelo usuário: o objetivo é recriar uma seção inteira em um clique.

## Design

### Cartão de inspeção (fase `selecting`)

- Mora num elemento próprio com shadow DOM fechado (`mode: "closed"`) no `documentElement`, com `pointer-events: none` e o maior `z-index`, para o CSS da página não o afetar nem ele afetar a página. Posiciona-se ao lado do elemento sob o mouse, dentro da viewport, e passa para o outro lado se não couber.
- Atualiza em `pointermove`, foco e `↑`, e a cada quadro de animação enquanto o elemento tem animações ativas (para a linha de animação acompanhar).
- Conteúdo, nesta ordem: nome curto (`tag.classe-principal`) e tamanho `largura × altura` em CSS px; fonte (`família`, `tamanho/altura de linha`, peso); cápsulas de cor para texto, fundo e borda, com o hex embaixo (cor transparente aparece como "transparente", nunca como hex vazio); raio, opacidade, transform e sombra quando diferentes do padrão; animações em curso (duração, easing); a dica "Clique ou Enter para fixar · ↑ pai · Esc cancela". Não mostra o texto do elemento.
- Os valores vêm das mesmas funções usadas na gravação (`styles()` e `rect()`), para o cartão e o brief nunca divergirem.
- Visual: o do Poach, como descrito nas metas. Cantos de 14 px, sombra suave, tipografia do sistema; sem dependência externa.
- O banner atual ("Click or Tab to select…") passa a ser a dica dentro do cartão quando há elemento sob o mouse, e continua como banner quando não há.

### Medição dos descendentes (`components`)

- Ao fixar, a extensão percorre os descendentes do elemento raiz e guarda até **40** componentes, em ordem de documento, com profundidade máxima 6. Se houver mais de 40, ficam os de maior área visível, com texto próprio primeiro como critério de desempate; a ordem de documento é mantida na saída.
- Entram só descendentes visíveis (tamanho maior que zero, `visibility` visível, `checkVisibility` verdadeiro) e fora de `input`, `textarea`, `select`, `[contenteditable]`, `[hidden]`, `[aria-hidden=true]`, `script` e `style`, as mesmas exclusões de `visibleText()`.
- Cada componente: `id` (índice), `parent` (índice do pai na lista, ou -1 para filho direto da raiz), `target` (`tag`, `role`, `classes`), `rect` relativo ao canto superior esquerdo da raiz, `styles` (as 17 propriedades), `text` (texto próprio do elemento, até 80 caracteres, vazio se não houver).
- São medidos **duas vezes**: ao fixar (`components`) e ao finalizar (`componentsAtEnd`), para o assistente ver o que mudou na estrutura. Ambos são opcionais e podem faltar em sessões antigas.
- Orçamento: cerca de 650 bytes por componente, 40 componentes, 2 listas: cerca de 52 KiB, bem abaixo dos 256 KiB. Se o corpo passar do limite mesmo assim, a extensão remove `componentsAtEnd` e tenta de novo antes de desistir (hoje desiste sem enviar nada).

### Contrato e servidor

- `bridge/evidence.py` aceita `components` e `componentsAtEnd` (até 40 itens cada, campos validados como os demais, `extra="forbid"` como o resto do modelo). Sessões sem esses campos continuam válidas.
- O corte à janela da gravação (`_trim`) não mexe nos componentes: não têm tempo.
- O brief passa a levar esses campos no `browserEvidence`, sem mudança em `Controller`.

### MCP e prompt

- `anypoach_read_brief` mostra um resumo de uma linha dos componentes (quantidade, página e origem) e entrega a lista completa no conteúdo estruturado, que já é o `browserEvidence` do brief.
- `anypoach_read_moment` não repete a lista (ela não depende do tempo); continua com os estados, eventos e animações próximos do instante.
- A frase do prompt de handoff passa a citar `evidence.browserEvidence.components` como a estrutura medida do componente.
- Os modelos continuam `extra="ignore"`; sessões antigas seguem lendo.

### Fluxo do usuário

1. No popup, "Choose a component" (o rótulo não muda).
2. Na página, o contorno e o cartão seguem o mouse. ↑ sobe ao pai. Clique ou Enter fixa.
3. A sessão começa (como hoje) e já leva os `components` medidos nesse instante.
4. O usuário grava no AnyPoach, faz a interação e finaliza no popup. A janela mostra "A Chrome session matches this recording and will be included".

## Privacidade

O cartão mostra valores só na tela local; nada é enviado antes de fixar. Ao fixar, os dados vão apenas ao servidor em loopback, protegidos pelo código de pareamento, e ficam em memória por 180 s como hoje. O texto dos descendentes é limitado a 80 caracteres, exclui campos de formulário e elementos ocultos, e entra no brief como o texto da raiz já entra. A regra do `AGENTS.md` sobre evidência do Chrome continua valendo sem mudança.

## Testes (o que o construtor deve cobrir)

- Chrome headless: uma página com uma seção de filhos conhecidos; após fixar, `components` traz tamanho, fonte e cor esperados, no máximo 40, sem campos de formulário nem elementos ocultos e com `parent` coerente.
- Chrome headless: o cartão mostra os valores do elemento sob o mouse e não aparece depois de fixar (nem no DOM).
- Chrome headless: uma página com mais de 40 descendentes mantém os maiores e a ordem de documento.
- Servidor: sessão com `components` válida é aceita; com 41 itens, campo desconhecido ou `parent` fora do intervalo é recusada com 422; sessão sem os campos continua aceita.
- MCP: o resumo aparece no `read_brief`; `read_moment` não repete a lista; sessões antigas seguem lendo.
- Orçamento: uma lista de 40 componentes com todos os campos no tamanho máximo cabe em 256 KiB junto com 48 estados e 16 animações.

## O que fica para o construtor

Pontos pequenos que o construtor decide sem voltar ao usuário: a regra exata de "classe principal" no nome curto, o posicionamento fino do cartão, a ordem dos campos no cartão quando faltam valores, e como medir a área visível quando o elemento está parcialmente fora da viewport.
