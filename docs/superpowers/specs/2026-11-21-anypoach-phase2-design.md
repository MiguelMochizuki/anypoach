# AnyPoach fase 2: Wayland, editor e o resto da v1

Data: 2026-11-21. Estado: rascunho para aprovação. Continua o design de `2026-11-20-poach-portable-rewrite-design.md`.

## Intenção e motivo

A fase 1 entregou a fatia vertical em Windows e Linux X11. Quem usa Linux com Wayland (o caso da máquina de desenvolvimento) ainda não consegue gravar, e o fluxo termina numa janela mínima, sem comentários na timeline. A fase 2 fecha essas duas lacunas. O comportamento do app original (histórico git, antes do commit `90e52d4`) é a referência de filosofia: ferramenta pequena, privada, que entrega evidência a um assistente sem mandar nada para fora.

## Divisão

- **2a, Wayland:** captura pelo portal, seleção de área e trace de ponteiro. Plano e execução próprios, primeiro.
- **2b, resto:** tela cheia, editor com comentários, onboarding, modo janela e atalho global, nessa ordem. Plano próprio depois da 2a.

## Objetivos da 2a

- Gravar uma área no GNOME Wayland com o mesmo fluxo e o mesmo brief do X11.
- Um `PortalBackend` que implementa `CaptureBackend`, sem mudar `Recorder`, `Controller` nem o contrato do brief.
- `uv run anypoach` continua funcionando sem pacotes Python de sistema.

## Não objetivos e anti-objetivos

- Suporte garantido a KDE, Sway ou Hyprland: o código fala só com a API do portal, mas só o GNOME é testado.
- Hook global de mouse ou teclado, libei ou leitura de botões fora do portal.
- Guardar permissão de captura sem consentimento explícito (regra de privacidade do `AGENTS.md`).

## Decisões do usuário

- Dividir a fase 2 em 2a e 2b, começando pelo Wayland.
- GNOME como alvo testado; os outros compositores, melhor esforço, com o README dizendo isso.
- Stream do PipeWire lido por subprocesso `gst-launch-1.0 pipewiresrc` com saída `rawvideo`; DBus do portal com `jeepney` ou `dbus-fast` (puro Python). Sem `PyGObject`.
- Área no Wayland: o primeiro quadro do stream congelado numa janela fullscreen do Qt, o usuário arrasta a área e o recorte é nosso.
- Ponteiro: trace `available: true` só com movimentos (cursor em metadado), se a medição mostrar que é confiável; senão `available: false`.
- `restore_token` do portal: desligado de fábrica. Opt-in numa configuração; guardado em `0600` no cache, com botão para apagar.
- Ordem da 2b: tela cheia, editor, onboarding, modo janela, atalho global.

## Abordagens consideradas (captura do stream)

- **A. `PyGObject` com GStreamer em processo:** o mais direto, mas só existe no Python do sistema e quebra `uv run anypoach`.
- **B. Subprocesso `gst-launch-1.0` lendo quadros do stdout:** mantém o `uv`, isola o GStreamer. Custo: dependência de sistema (`gstreamer1.0-pipewire`) e metadado de cursor possivelmente inacessível.
- **C. Binding direto de PipeWire:** sem opção madura em Python.

**Escolhida: B**, por decisão do usuário.

## Design da 2a

1. **`PortalClient`:** `CreateSession`, `SelectSources` (monitor, `cursor_mode=Metadata`, sem `persist_mode` por padrão), `Start`, `OpenPipeWireRemote`. O consentimento é da caixa do portal; cancelar vira `PermissionError`.
2. **`PipeWireStream`:** inicia `gst-launch-1.0` com o fd do remoto, lê quadros BGRA do stdout em uma thread e guarda o último com o tempo do relógio monotônico, como o `MssBackend` faz.
3. **`PortalBackend`:** `screens()` devolve o monitor do stream com `scale`; `grab(region)` devolve o último quadro recortado. Se o stream parar, levanta `PermissionError` ou `OSError` e o `Controller` mostra a mensagem.
4. **Seleção:** no Wayland, a janela de seleção usa o primeiro quadro congelado em fullscreen. Em X11 e Windows nada muda.
5. **Ponteiro:** `PortalPointerSource` implementa `PointerSource` com a posição do metadado do cursor, sem botões. A viabilidade é a primeira tarefa do plano (spike); o resultado decide entre `available: true` com movimentos e `available: false`.
6. **Escolha do backend:** `XDG_SESSION_TYPE=wayland` seleciona o portal; `QT_QPA_PLATFORM` e o resto seguem como estão.

## Critério de pronto da 2a

No GNOME Wayland: gravar 10 s de uma área, obter keyframes e paleta, gerar o brief e lê-lo por `anypoach_read_brief` e `anypoach_read_moment` com um cliente MCP real. O handoff diz com precisão o que o trace contém.

## Teste

- Portal falso no barramento de sessão (`dbus-daemon` no CI Linux) para `PortalClient`.
- `gst-launch-1.0 videotestsrc` no lugar do `pipewiresrc` para `PipeWireStream`.
- Verificação manual no GNOME Wayland, a única que cobre o portal real e o metadado do cursor.

## Comportamento de referência para a 2b

- **Editor:** comentário preso a um instante; marcadores na timeline, agrupados quando a menos de 24 px; lista lateral com campo para escrever, remoção por comentário; visitar um comentário pausa, posiciona o vídeo e destaca o texto por 3 s; play/pause, arrastar a timeline pausa e retoma.
- **Atalho global:** só o acorde de captura, nunca o teclado. Windows `RegisterHotKey`, X11 `XGrabKey`, Wayland pelo portal `GlobalShortcuts` onde existir. Equivalente de `Cmd+Shift+P`: `Ctrl+Shift+P`.
- **Modo janela:** grade de prévias com título e app; escolher e confirmar com Enter.
- **Onboarding:** boas-vindas e conexão do assistente, com "pular".

## Riscos

- **Cursor em metadado:** o `gst-launch` pode não expor o metadado do cursor. O spike decide; o plano degrada para `available: false`.
- **Latência e CPU:** o caminho do subprocesso passa os quadros brutos por um pipe; medir contra a linha de base do `mss`.
- **Variação de portais:** GNOME e KDE diferem em versão, persistência e picker.
- **Dependência de sistema:** `gstreamer1.0-pipewire` precisa estar instalado; o app detecta e explica a falta.

## Ficou para o construtor

Escolha entre `jeepney` e `dbus-fast`, formato do pipe (`rawvideo` por fd ou stdout), nomes dos módulos em `anypoach.capture`, e como pedir a primeira confirmação do portal na janela.

## Minhas decisões (marcar se discordar)

- O atalho no Windows e no Linux é `Ctrl+Shift+P`.
- A seleção congelada também serve de prévia no modo tela cheia no Wayland.
- A 2b só ganha plano depois de a 2a estar mergeada e medida.
