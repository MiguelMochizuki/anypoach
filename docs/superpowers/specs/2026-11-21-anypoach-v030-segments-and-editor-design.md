# AnyPoach v0.3.0: trechos de movimento e editor de comentários

Data: 2026-11-21. Estado: aguardando aprovação do usuário. Continua `2026-11-21-anypoach-fidelity-design.md` (Design B) e `2026-11-21-anypoach-phase2-design.md` (comportamento de referência da 2b). Recorte escolhido pelo usuário: v0.3.0 = trechos de movimento + editor de comentários; o resto da 2b vai para a v0.4.0 e o instalador para a v0.5.0.

## Intenção e motivo

O objetivo do projeto é que o AnyPoach substitua o Poach de ponta a ponta, em qualquer sistema, e que isso saia em releases rápidos. Duas lacunas pesam mais para quem grava uma interação e a entrega a um assistente:

- **O assistente lê um só movimento por vídeo.** O corte de "movimento relevante" é 12% do maior pico do vídeo inteiro (`choose_keyframes`), então numa gravação com uma rolagem grande e um hover pequeno o hover some, e há um `timing` só para tudo. O documento de fidelidade do Poach avisa que ler essa estimativa como a duração de uma interação específica dá resultado errado.
- **Não existe forma de escrever notas.** O brief já carrega `context` e `annotations` (`[{timeMs, text}]`) e o servidor MCP já mostra as notas perto de cada instante, mas a janela nunca preenche nenhum dos dois: o README promete "your notes" e o app não tem onde digitá-las. O Poach tem editor com comentários presos à timeline.

## Objetivos

- Um brief de gravação com várias interações descreve cada uma: início, pico, assentamento e timing próprios.
- Quem grava consegue, depois de parar, rever o vídeo, comentar qualquer instante e escrever instruções gerais, e o assistente recebe isso pelo caminho que já existe (`annotations`, `context`).
- Tudo que não depende de uma tela real é testado no CI, e o que depende fica numa lista de checagens manuais.
- Gravações de uma interação só continuam produzindo exatamente o mesmo `keyframes` e `timing` de hoje (os goldens congelados não mudam).

## Não objetivos e anti-objetivos

- Separar duas interações que acontecem ao mesmo tempo na tela: viram um trecho só.
- Importar vídeo ou imagem, screenshot, tela cheia, modo janela, atalho global, bandeja e onboarding: v0.4.0.
- Paleta ajustável (o Poach tem): fica para a v0.4.0 junto das opções do editor; a v0.3.0 só mostra a paleta que já mostra.
- Reproduzir o vídeo com som, exportar o vídeo, ou editar o vídeo.
- Qualquer chamada de rede, telemetria ou retenção nova (`AGENTS.md`). Os comentários só viajam dentro do brief que o usuário compartilha, com a mesma expiração de 24 h.
- Anti-objetivo: um preparo de quadros que trava a janela num clipe de 30 s, ou um editor que só funciona onde o decodificador de vídeo do sistema por acaso funciona.

## Abordagens consideradas

**Trechos de movimento.** Um caminho só: dividir a série de diferenças entre quadros em trechos e reaproveitar `choose_keyframes` em cada trecho. Reaproveitar a função garante que um vídeo com uma interação dá o resultado de hoje, e que a regra "12% do pico" passa a valer dentro do trecho em vez de no vídeo todo. Mexer na função em si ou reescrevê-la foi descartado porque os goldens dependem do comportamento exato dela.

**Editor de comentários.**
1. *Player do Qt (`QtMultimedia`) com timeline própria.* Toca o vídeo de verdade, mas o decodificador varia por sistema e o playback não é testável sem tela.
2. *Sem player do Qt: o nosso decodificador (PyAV) alimenta os quadros.* Escolhida pelo usuário. Total controle, testável no CI, o mesmo decodificador que a análise já usa em todos os sistemas. Custo: o play é um temporizador que avança quadros de um proxy reduzido, não vídeo em tempo real.
3. *Comentar só sobre os keyframes.* Descartada: é um retrocesso em relação ao Poach, que comenta em qualquer instante.

Se o `QtMultimedia` se mostrar estável nos três sistemas, trocar a fonte dos quadros depois é uma mudança local, porque a timeline fala com uma interface de "quadro mais próximo deste instante".

## Design A: trechos de movimento

1. **Detecção** em um módulo novo `analysis/segments.py`: dado `deltas` e `times_ms` (o que `inspect_video` já calcula), devolve a lista de trechos. Um quadro é "ativo" quando a diferença passa de um piso absoluto (0,008, o mesmo mínimo que `choose_keyframes` já usa); corridas ativas separadas por menos de 400 ms viram um trecho; cada trecho recebe uma folga de 250 ms (em tempo, não em amostras, porque a taxa de amostragem cai em vídeos longos) depois do fim para o assentamento. `choose_keyframes` roda sobre a fatia de cada trecho, então o "12% do pico" e o assentamento passam a ser locais. A `strength` de um trecho é o maior `delta` dentro dele (o pico).
2. **`timing` por trecho** com `approximate_timing`, sobre o trecho.
3. **Compatibilidade:** `keyframes` e `timing` do topo continuam sendo calculados **sobre a série inteira, como hoje, pelo mesmo código**, então qualquer vídeo dá exatamente o resultado de antes e os goldens de `tests/golden` não mudam, mesmo que haja movimento residual (cursor, cursor de texto, ruído de codec) acima do piso. O trecho que contém o pico global usa esses `keyframes` e esse `timing` do topo tal e qual (os mesmos arquivos PNG, sem duplicar). Por isso um vídeo com movimento residual pode ter mais de um trecho em `segments` sem que o topo mude. Um vídeo parado (nada acima do piso) tem `segments: []` e o topo continua sendo o quadro `start` de hoje.
4. **Campo novo** `evidence.segments`, em ordem de tempo, até 12 (os 12 mais fortes por `strength` quando houver mais): `{startMs, peakMs, endMs, strength, timing: {durationMs, bezier, token}, keyframes}`. `keyframes` (a lista de `{kind, timeMs, imagePath, motion}` de hoje) vem preenchida só para os 4 trechos mais fortes; nos demais é `[]` e o assistente pede o quadro com `anypoach_read_moment`. As PNGs só são gravadas para esses 4.
5. **MCP:** quando `segments` existe, `anypoach_read_brief` devolve as imagens dos trechos que as têm, em ordem de tempo, no máximo 12 por resposta (4 trechos x 3 quadros); as do topo são as mesmas do trecho mais forte e por isso não vêm repetidas. O limite "Too many keyframes" (hoje 3) passa a ser 12 e vale para as imagens de uma resposta; `keyframes` do topo no brief continua com no máximo 3, e leitores antigos, que só leem o topo, continuam funcionando. O texto de `segments` entra no JSON que a ferramenta já devolve. `anypoach_read_moment` não muda.
6. **Prompt do handoff:** uma frase nova diz que a gravação pode ter várias interações, que cada trecho tem o seu timing, e que ler o timing de um como o de outro é o erro a evitar.
7. **Brief antigo** (sem `segments`) continua sendo lido sem erro; a versão do brief continua `1`.

## Design B: editor de comentários

1. **Quando aparece:** depois de parar e analisar, a janela mostra o painel de revisão no lugar da faixa de keyframes (a faixa continua disponível como lista). Antes de gravar nada muda.
2. **Quadros:** um módulo novo `analysis/proxy.py` decodifica a gravação uma vez, depois do `stop`, numa thread de fundo, para quadros reduzidos (lado maior 640 px, 15 por segundo, guardados como JPEG em memória, qualidade 80, uns 30 KB cada), cada um com o seu instante real de apresentação (PTS, em ms, a partir do zero do vídeo, o mesmo eixo de `anypoach_read_moment`). A duração vem da mesma `VideoSource` que a análise usa. O limite de 30 s da análise já vale para a gravação, então o teto natural é 450 quadros e não há caso de "vídeo maior que o proxy". A timeline sempre aponta para um quadro do proxy: arrastar encaixa no quadro mais próximo. Enquanto o proxy não terminou, o painel diz "preparando quadros", os quadros já prontos podem ser vistos e o botão de comentar fica desligado. A thread é cancelada (um `Event` verificado a cada quadro) ao começar outra gravação ou fechar a janela. Copiar o handoff funciona a qualquer hora, com o proxy pronto ou não, porque não depende dele. Sem rede, sem disco.
3. **Timeline** (widget próprio): trilha com o instante atual, faixas dos trechos de movimento desenhadas atrás (vêm de `evidence.segments`) e marcadores dos comentários; marcadores a menos de 24 px se agrupam em um com contador. A lógica de agrupar é uma função pura (`group_markers(times_ms, duration_ms, width_px, min_gap_px=24)`).
4. **Reproduzir:** botão play/pausa e barra de espaço; um temporizador avança os quadros do proxy na cadência original; arrastar a timeline pausa e retoma se estava tocando; terminar volta ao início e pausa. Setas esquerda e direita andam um quadro do proxy.
5. **Comentários:** campo de texto e botão "Comentar neste instante" criam `{timeMs, text}` no instante do quadro atual (o PTS desse quadro do proxy em milissegundos inteiros, o mesmo eixo que `anypoach_read_moment` usa); lista lateral ordenada por tempo, cada item com botão de remover; clicar num item pausa, posiciona o vídeo naquele instante e destaca o texto por 3 s. Limites: 500 caracteres por comentário e 50 comentários por gravação; texto vazio é recusado com mensagem.
6. **Instruções gerais:** um campo de texto que preenche `Controller.context`.
7. **Modelo no `Controller` (sem Qt):** `add_comment(time_ms, text) -> bool`, `remove_comment(index)`, `comments` (cópia ordenada por `timeMs`), e `annotations` passa a ser mantido por eles. Começar uma nova gravação limpa os comentários (os instantes pertencem ao vídeo antigo) e mantém as instruções gerais. `copy_handoff` já compartilha ambos.
8. **Acessibilidade:** todo controle tem nome acessível; a janela continua operável só com teclado (Tab até a timeline, setas, Enter para comentar).

## Testes

- `segments`: clipes sintéticos de `tests/fixtures.py` com 1, 3 e 12 ou mais interações; um hover pequeno ao lado de uma rolagem grande, separados no tempo, vira dois trechos; dois movimentos colados (menos de 400 ms) viram um; um clipe parado dá zero trechos além do `start`; os goldens existentes ficam idênticos.
- Brief e MCP: round-trip de `evidence.segments`, brief antigo sem `segments` lido sem erro, limite de 12 imagens, imagens só para os 4 trechos mais fortes.
- `proxy`: a quantidade e o tempo dos quadros contra um vídeo conhecido; quadro mais próximo de um instante.
- `Controller`: adicionar, remover, ordenar, limites, texto vazio, limpar ao regravar, comentários e instruções chegam ao brief compartilhado.
- Widgets (Qt offscreen): `group_markers`, navegação por teclado, nomes acessíveis, destaque de 3 s com relógio injetado, play/pausa com temporizador falso.
- Manuais (um humano, em tela real): o play não engasga em 1080p de 30 s, o arrastar da timeline responde, nada trava a janela durante o preparo do proxy.

## Riscos

- **Memória e tempo do proxy:** 450 quadros de 640 px em JPEG ficam em torno de 15 MB; decodificar 30 s de 1080p custa uns 7 s (`baseline.md`), em segundo plano. Medir antes de fechar os números.
- **Calibração dos trechos** só com fixtures sintéticas: gravações reais (rolagem contínua, vídeo na página) podem gerar trechos demais; o teto de 12 e a mescla de 400 ms seguram o estrago, e os números são fáceis de ajustar.
- **Resposta grande do MCP:** 12 imagens por `anypoach_read_brief`; cada uma segue o teto de 5 MB e a redução para 1280 px.

## Ficou para o construtor

Valores finos dos limiares (piso 0,008, mescla de 400 ms, folga de 3 amostras) depois de olhar as fixtures; nomes dos módulos e das classes dos widgets; thread de fundo com `QThread` ou `concurrent.futures`; aparência e layout do painel; texto exato das mensagens e do prompt.

## Minhas decisões (marcar se discordar)

- Paleta ajustável fica para a v0.4.0.
- O topo (`keyframes`, `timing`) continua calculado sobre a série inteira; o trecho do pico global reaproveita esse resultado. A `strength` é o pico do trecho, e a folga pós-trecho é de 250 ms.
- Os trechos aparecem como faixas na timeline do editor (custo baixo, e mostra onde estão as interações).
- Limites de 500 caracteres por comentário e 50 comentários; começar nova gravação limpa os comentários e mantém as instruções gerais.
- Proxy de 640 px, 15 quadros por segundo, 450 no máximo, JPEG em memória.
- Piso de 0,008 e mescla de 400 ms como pontos de partida.
- `anypoach_read_brief` devolve as imagens dos trechos no lugar das do topo quando `segments` existe.
