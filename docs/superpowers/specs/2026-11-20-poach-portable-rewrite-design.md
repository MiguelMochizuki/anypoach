# Poach portátil: design da reescrita em Python

Data: 2026-11-20. Estado: rascunho para aprovação.

## Intenção e motivo

O Poach hoje só roda no macOS: captura (ScreenCaptureKit), UI (SwiftUI), atalho e ícone de menu são específicos da Apple. O objetivo é que qualquer pessoa, em Windows, Linux ou macOS, consiga gravar uma interação de UI, anotar e entregar a evidência a um assistente de código. Sucesso é uma pessoa de Windows ou Linux fazer esse fluxo de ponta a ponta. Um MCP portátil sem captura não atende.

Motivo secundário: eficiência. `inspectVideo` abre um processo `ffmpeg` por amostra (até 720 por análise) e a distribuição embute Node + ffmpeg + ffprobe. Decodificar e comparar quadros em um único processo elimina esse custo.

## Objetivos

- Uma base de código para os três SOs, em Python, substituindo o app Swift, o núcleo TypeScript e o servidor MCP TypeScript.
- Fluxo v1: gravar (área ou tela cheia) → trace de ponteiro → análise (keyframes, paleta, timing) → brief → leitura pelo servidor MCP → editor com comentários na timeline.
- Contratos externos inalterados: JSON do brief v1, formato `.poach`, nomes e schemas das tools MCP (`poach_inspect`, `poach_inspect_image`, `poach_read_brief`, `poach_read_moment`), protocolo HTTP da extensão Chrome (porta 47831, `/v1/capture`, Bearer). A extensão `apps/chrome` é reaproveitada sem mudança.
- Menos latência de análise e menos tamanho de distribuição. Metas numéricas só depois da linha de base.

## Fora de escopo (v1)

Chrome companion, favoritos, atualizações automáticas, font matcher, design lab. Ordem posterior: Chrome companion, favoritos, atualizações, font matcher. Backends de captura nativos por SO. Wayland nativo completo (ver restrições).

## Anti-objetivos

- Funcionar só no papel: um fluxo que passa nos testes mas não grava no Windows ou no Linux de verdade.
- Quebrar compatibilidade com briefs, `.poach` ou connectors existentes.
- Qualquer rede, telemetria, retenção persistente, áudio, hook global de teclado/mouse ou leitura de teclado. As regras de privacidade do `AGENTS.md` continuam valendo.

## Restrições

- Recursos de segurança mantidos: vídeo até 30 s e 512 MiB; gravação até 1920 px e 30 fps; análise a 12 amostras/s, no máximo 720; trace a 120 Hz, no máximo 5.000 eventos; brief com validade de 24 h; arquivos só do usuário (`0700`/`0600`, ACL restrita no Windows); mídia de qualquer brief válido protegida contra limpeza.
- Ponteiro por polling via `ctypes` (`GetCursorPos`/`GetAsyncKeyState`, `CGEventSource`, `XQueryPointer`), sem hooks. Atalho global só pelo registro nativo do chord (`RegisterHotKey`, `XGrabKey`).
- Wayland: captura via `xdg-desktop-portal`; sem posição do ponteiro o trace sai com `available: false` e o handoff diz isso.
- Mínimos de SO: Windows 10 21H2+, macOS 12+, Ubuntu 22.04+.
- Apache-2.0 mantida, com `LICENSE` e `NOTICE` registrando a origem. Nome e logo só em binários publicados depois de combinar com o autor original.
- Teste local só em Linux. Windows e macOS dependem de CI nos três SOs ou de máquina do usuário.

## Abordagens consideradas

- **A. Por camadas** (baseline → análise/MCP → captura → UI): bem testada, mas só entrega valor ao usuário no fim e esconde os riscos de captura até o meio.
- **B. Fatia vertical primeiro:** fluxo mínimo de ponta a ponta no Windows e no Linux X11, depois alargar. Expõe cedo os riscos de captura e PTS e dá algo executável a quem não tem Poach hoje. Custo: parte da UI e da captura da fatia é refeita ao alargar.
- **C. Tradução fiel tela a tela:** menor risco de design, mas é o mais lento e carrega hábitos do macOS.

**Escolhida: B**, por decisão do usuário.

## Decisões do usuário

- Linguagem: Python com PyAV e numpy, sem `ffmpeg`/`ffprobe` externos nem Node. Núcleo nativo só se a medição contra a linha de base exigir.
- UI: PySide6. Servidor MCP em entry point separado e leve (`mcp`, `av`, `numpy`), instalável por `uv`/`pipx` e também empacotado no app. Empacotamento do app com PyInstaller.
- Captura: interface `CaptureBackend`; v1 com lib portável (`mss`/`dxcam` + codificação PyAV). Cursor e anel de clique desenhados por nós a partir do trace. Janelas do Poach escondidas durante a gravação, com `WDA_EXCLUDEFROMCAPTURE` ou equivalente onde existir.
- Modos: área e tela cheia em todos os SOs; janela onde houver listagem confiável (Windows, macOS); no Linux, via picker do portal.
- Handoff: o prompt é sempre copiado; o app do assistente só é aberto quando detectável.
- Connector: comando copiável (`claude mcp add poach -- uvx poach-mcp`, equivalente do Codex) e `.mcpb`. A app só mostra o estado de conexão pelos arquivos em `connections/`.
- Migração: código novo em `python/` ao lado do atual. `packages/core` é o oráculo; fixtures sintéticas e goldens gerados com ele, comparados com tolerância. Swift e TS só saem depois de o Python passar nos goldens e num teste ponta a ponta. Testes de brief rodam em CI nos três SOs.

## A fatia vertical (fase 1)

Plataformas: Windows 10+ e Linux X11. Entrega:

1. **Linha de base e goldens.** Medir `inspectVideo` atual (tempo, memória) em fixtures sintéticas e gerar os goldens (paleta, keyframes, timing, `motion`).
2. **Análise em Python.** Portar `extractor`, `motion`, `palette` em um processo: decodificação por PyAV, comparação por numpy, PTS preservado para o equivalente de `seekForMoment`.
3. **Brief e servidor MCP.** Escrever e ler o brief v1 no diretório de cache do SO; as quatro tools; arquivo de presença em `connections/`.
4. **Captura e ponteiro.** `CaptureBackend` portável, gravação de uma área a 30 fps, trace a 120 Hz, cursor e anel desenhados a partir do trace, janelas do Poach fora do vídeo.
5. **Janela mínima.** Escolher área, gravar, parar, ver o resultado, copiar o handoff. Sem atalho global, sem onboarding.

Critério de pronto da fase 1: em Windows e em Linux X11, gravar 10 s de uma área, obter keyframes e paleta dentro da tolerância dos goldens, gerar um brief e lê-lo por `poach_read_brief` e `poach_read_moment` com um cliente MCP real.

## Fases seguintes

Fase 2: editor com comentários e timeline, tela cheia, atalho global, modo janela, onboarding e Wayland (captura via `xdg-desktop-portal` ScreenCast e PipeWire, num `PortalBackend` ao lado do `MssBackend`, com seleção de área e trace de ponteiro adaptados ao portal). Fase 3: macOS no código novo. Fase 4: extras, na ordem acima. O código Swift e TS original já foi removido do repositório.

## Riscos

- **PTS fiel:** o `seekForMoment` assume timestamps reais do ScreenCaptureKit; na captura portátil o PTS vem do nosso relógio, e quadros repetidos devem preservar seus tempos. A fatia valida isso primeiro.
- **HiDPI e multi-monitor:** o trace é normalizado pelos limites capturados; escala por monitor e coordenadas lógicas vs físicas precisam de testes por SO.
- **Polling a 120 Hz em Python:** depende do GIL e do agendador de cada SO; medir jitter e perda de amostras.
- **Tamanho do pacote com Qt:** medir antes de prometer distribuição pequena.
- **Wayland:** sem ponteiro e com picker por sessão; fora da fatia.

## Ficou para o construtor

Estrutura interna de `python/` (proposta: `src/poach/{analysis,brief,capture,pointer,mcp,ui}`, `uv` workspace, `pytest`, `ruff`), escolha entre `mss` e `dxcam` por SO, esquema de CI, metas numéricas depois da linha de base e detalhes de ACL no Windows.

## Minhas decisões (marcar se discordar)

- Sem atalho global e sem onboarding na fatia.
- O editor com comentários fica na fase 2, não na fatia.
- Linha de base medida no Linux, com o `inspectVideo` atual; o macOS fica como referência de comportamento, não de desempenho.
- Goldens com tolerância: paleta e tempos exatos, `motion` com epsilon.
