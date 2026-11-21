# AnyPoach: pacote de fidelidade, extensão do Chrome e trechos de movimento

Data: 2026-11-21. Estado: aguardando aprovação do usuário. Parte do item 1 e do item 3 de `docs/superpowers/poach-parity.md`.

## Intenção e motivo

Quem grava uma interação quer que o assistente a recrie no tamanho certo. Hoje a recriação sai "levemente maior ou menor", e o motivo foi medido: uma gravação de 1854x962 chega ao assistente como PNG de 1280x664, e nada no brief diz isso. O assistente mede na imagem reduzida e monta a página para uma janela de 1280 px. Uma segunda queixa vem junto: numa gravação com várias interações, só a de maior mudança é descrita (3 keyframes e um timing por vídeo).

O Poach original tem as duas limitações: reduz a 1280 px sem avisar (`extractor.ts`) e dá uma estimativa de timing para o vídeo inteiro, coisa que o próprio documento de fidelidade dele admite que induz a erro. O que o Poach faz melhor é a extensão do Chrome, que lê os valores reais de uma interface web em vez de adivinhá-los em pixels de vídeo. Um app que só um Mac enxerga e que ainda precisa de um plugin para acertar o tamanho de um botão: o AnyPoach entrega o plugin também, e em qualquer sistema.

## Fatos verificados no código

- Os keyframes são gravados em disco já reduzidos (`png_at`, `max_size=1280`, em `analysis/source.py`); o MCP só lê esses PNGs.
- O brief não tem tamanho da captura. O único tamanho é `boundsWidth`/`boundsHeight` dentro do `pointerTrace`, que não existe no Wayland nem no macOS.
- `evidence` aceita campos novos: o modelo `Brief` ignora extras, então briefs e leitores antigos continuam funcionando.
- O servidor MCP recusa mais de 3 keyframes e cada imagem tem teto de 5 MB.
- O corte de "movimento relevante" é 12% do maior pico do vídeo; por isso um hover pequeno ao lado de uma rolagem grande some.
- A escala do monitor é conhecida no X11 e no Windows (Qt). No Wayland o portal informa só o tamanho do stream, e o GNOME pode informar tamanho lógico.

## Divisão e ordem de entrega

- **v0.1.0 (pré-release):** pacote A, tamanho real e escala (abaixo).
- **v0.2:** extensão do Chrome (servidor local, pareamento, `evidence.browser`) e, no macOS, ponteiro por `CGEventSource` e aviso de permissão de gravação de tela.
- **v0.3:** pacote B, trechos de movimento múltiplos, e a fase 2b (editor com comentários, atalho global e bandeja, onboarding, modo janela).

Cada uma ganha plano próprio. A 2b só ganha plano depois de a v0.2 estar mergeada e medida.

## Decisões do usuário

- Q1: só o pacote A bloqueia o v0.1.0; os trechos múltiplos ficam para depois.
- Q2: o brief informa o tamanho real e cada imagem ganha legenda; `anypoach_read_moment` ganha `maxSize` e `crop` para ampliar um detalhe em escala nativa.
- Q3: `deviceScale` vem preenchido quando conhecido e `null` quando não; o prompt do handoff manda perguntar quando for `null`. Nunca se assume 1.0.
- Q4: o JSON lista todos os trechos (até 12); as imagens vêm só para os 4 mais fortes, 3 quadros cada; os demais se pedem com `anypoach_read_moment`. `keyframes` e `timing` de hoje continuam sendo os do trecho mais forte.
- Q5: extensão própria, copiada do código do Poach (Apache-2.0, coberto pelo `NOTICE`), renomeada e em outra porta (47832), com o mesmo formato de mensagens.
- Q6: o servidor HTTP mora dentro do processo da janela e só escuta enquanto o AnyPoach está aberto, em `127.0.0.1`, com código de pareamento.
- Q7: a evidência do navegador entra no brief como `evidence.browser`, e o prompt manda preferir esses valores aos medidos no vídeo.
- Q8: a extensão vai desempacotada dentro do pacote Python, com botão "Abrir pasta da extensão" e passos no README; a Chrome Web Store fica para quando o fluxo estiver estável.
- Q9: v0.1.0 só com o pacote A; extensão logo depois.
- Go: não agora. A decodificação e a codificação já rodam em C (PyAV, libx264, numpy). Antes do release se mede um clipe de 1920x1080 e 30 s e uma gravação real no Wayland, e os números entram em `baseline.md`; só um perfil que aponte código Python nosso como gargalo reabre a conversa, e então a opção é Rust via `maturin`.

## Design A: tamanho e escala (v0.1.0)

1. **Campo novo** `evidence.capture`, opcional:
   `{"widthPx": 1854, "heightPx": 962, "deviceScale": 1.0 | null, "imageMaxSize": 1280}`.
   `widthPx` e `heightPx` vêm do `VideoSource` (tamanho nativo do vídeo), então existem também sem trace e em qualquer plataforma. `deviceScale` vem do Qt no `Controller` (X11 e Windows) e é `null` no Wayland. Vídeos e imagens importados de fora não têm escala conhecida: `null`.
2. **Legendas das imagens:** o texto que precede cada imagem em `anypoach_read_brief` e `anypoach_read_moment` diz o tamanho da imagem, o nativo e o fator, por exemplo `1280x664, reduzida de 1854x962 (x0,69)`. Imagem que já está em tamanho nativo diz só `1854x962, tamanho nativo`.
3. **`anypoach_read_moment`:** parâmetros opcionais `maxSize` (até o tamanho nativo; padrão 1280, como hoje) e `crop` (`{x, y, width, height}` em pixels nativos). O recorte é feito antes da redução, e a legenda informa o retângulo e a escala. O teto de 5 MB por imagem continua, e uma resposta maior é recusada com mensagem que sugere `crop` menor.
4. **Prompt do handoff** ganha duas frases: as medidas das imagens estão em pixels de captura, dividir por `deviceScale` para obter pixels CSS, e perguntar quando for `null`; e as imagens podem estar reduzidas, conferir a legenda antes de medir.
5. **Compatibilidade:** versão do brief continua `1`; briefs antigos não têm `capture` e o servidor MCP omite as legendas de escala neles, sem erro. Os goldens de `tests/golden` ganham `capture` e continuam idênticos no resto.

## Design da extensão do Chrome (v0.2)

1. **Extensão** em `src/anypoach/chrome_extension/` (MV3, JavaScript puro, sem build): `manifest.json`, `bridge.js`, `capture.js`, popup. Nome AnyPoach, `host_permissions` só para `http://127.0.0.1/*`. Funciona em Chrome, Edge e Brave.
2. **Servidor local** em `anypoach.bridge` (módulo novo, só biblioteca padrão: `http.server` em thread, escutando `127.0.0.1:47832`). Endpoints `GET /v1/pair`, `POST /v1/open-capture`, `POST /v1/capture` (JSON de até 256 KiB, cabeçalho `X-AnyPoach-Final`), todos com `Authorization: Bearer <código>`. O código é gerado na janela, guardado no cache em `0600` e pode ser trocado, o que invalida o antigo.
3. **Evidência:** a última evidência final é guardada por 180 s e alinhada ao intervalo da gravação; a que está fora da janela é descartada. Ao compartilhar, o brief ganha `evidence.browser` com estilos computados (`width`, `height`, `fontFamily`, `fontSize`, `fontWeight`, `lineHeight`, `letterSpacing`, `borderRadius` e os demais da lista da extensão), eventos do navegador, mudanças de estado visíveis e tempos de `transition` e `animation`, mais o `devicePixelRatio` da página.
4. **Prompt e MCP:** `anypoach_read_brief` devolve `evidence.browser` sem nova tool; o prompt diz que valor do navegador manda e o vídeo confirma.
5. **Interface:** na janela, seção "Chrome" com o código, o botão "Abrir pasta da extensão" e o estado do pareamento. Nada escuta quando o app está fechado.

## Design B: trechos de movimento (v0.3)

1. **Detecção:** `analysis/motion.py` passa a produzir segmentos, não só o pico: o limiar deixa de ser 12% do maior pico do vídeo e passa a ser local ao trecho, para que um hover pequeno ao lado de uma rolagem grande não suma. Mescla de trechos separados por menos de um intervalo curto, duração mínima e no máximo 12 trechos; limiares calibrados em clipes sintéticos, não em gravações do usuário.
2. **Campo novo** `evidence.segments`: lista de `{startMs, endMs, peakMs, strength, timing}`, em ordem de tempo. `keyframes` e `timing` de hoje continuam sendo os do trecho mais forte.
3. **Imagens:** os 4 trechos mais fortes entregam start, peak e settled; o limite de "mais de 3 keyframes" do servidor passa a 12 imagens por resposta. Os outros trechos ficam no JSON e se pedem com `anypoach_read_moment`.
4. **Prompt:** uma frase diz que a gravação pode ter várias interações e que cada trecho tem o seu timing; ler o tempo de um trecho como o de outro é o erro que o documento de fidelidade do Poach descreve.

## Não objetivos e anti-objetivos

- Reduzir menos as imagens por padrão: estoura o teto de 5 MB em telas grandes; o `crop` resolve o detalhe.
- Rede além do `127.0.0.1`, telemetria ou retenção: nada disso entra (`AGENTS.md`).
- Escutar na porta com o app fechado, ou aceitar evidência sem código de pareamento.
- Publicar na Chrome Web Store nesta rodada.
- Reescrever a análise em outra linguagem sem uma medição que a justifique.
- Garantir `deviceScale` no Wayland sem uma fonte confiável: continua `null`.

## Testes

- Fixtures sintéticas de `tests/fixtures.py`: um vídeo maior que 1280 px cobre a legenda e o `crop`; `capture` nos goldens.
- `read_moment` com `crop` e `maxSize` contra um vídeo conhecido: o retângulo devolvido tem o tamanho e a escala esperados, e um recorte fora do vídeo é recusado.
- Brief antigo (sem `capture`) lido pelo servidor MCP sem erro.
- Servidor da extensão: `http.client` contra o servidor real em thread (pareamento, 401 com código errado, 413 acima de 256 KiB, `final` versus parcial, descarte após 180 s com relógio injetado).
- Extensão: o JavaScript da captura roda em Chrome sem interface contra uma página de teste (estilos computados e eventos), uma vez na CI Linux.
- Trechos (v0.3): clipes sintéticos com 1, 3 e 12+ interações, uma pequena ao lado de uma grande, e dois movimentos colados que devem mesclar.

## Riscos

- **Escala no Wayland:** o tamanho do stream pode ser lógico; `deviceScale: null` evita uma escala errada em silêncio, ao custo de uma pergunta ao usuário.
- **Pareamento e porta ocupada:** se a 47832 estiver em uso, o app mostra a causa e não cai.
- **Pacote do brief inchado:** `segments` e `browser` crescem; o limite de 256 KiB da evidência e o de 12 trechos seguram o tamanho, e o servidor MCP recusa respostas acima dos 5 MB por imagem.
- **Extensão fora da loja:** "Carregar sem compactação" assusta quem não é desenvolvedor; o README explica passo a passo e a loja entra depois.

## Ficou para o construtor

Nomes exatos dos campos de `evidence.browser` (seguir os da extensão do Poach onde fizer sentido), formato do código de pareamento, política de coleta de eventos do navegador (limites de quantidade), valores dos limiares e do intervalo de mescla dos trechos, e como a legenda é escrita em português ou inglês no texto do MCP (hoje as mensagens do MCP são em inglês).

## Minhas decisões (marcar se discordar)

- O servidor da extensão usa só a biblioteca padrão e mantém o limite de 256 KiB e a janela de 180 s do Poach.
- A versão do brief continua `1`.
- A legenda das imagens fica em inglês, como o resto do texto do MCP.
- O `crop` e o `maxSize` entram no v0.1.0 junto com o resto do pacote A; o `maxSize` padrão continua 1280.
- A calibração dos limiares de trecho usa só fixtures sintéticas.
