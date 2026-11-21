# Paridade com o Poach original

Data: 2026-11-21. Estado: levantamento a partir do clone do original (README, código e `docs/fidelity-context-meter.md`); o app original só roda em macOS e não foi executado.

## Intenção

O Poach é uma boa ideia que mora numa barra de menu que só um Mac enxerga, e ainda pede macOS 15 para gravar direito. O AnyPoach existe para a mesma ideia valer em qualquer máquina. "Pau a pau" quer dizer: quem usa o AnyPoach não sente falta de nada que o Poach entrega, e em alguns pontos recebe mais.

## Onde o AnyPoach já está à frente

- Roda em Windows, Linux X11 e Linux Wayland (GNOME testado); o Poach só no macOS.
- Análise em um processo: 0,06 s e 0,17 s nos clipes pequenos de teste, contra 3,76 s e 33,5 s do `ffmpeg` por amostra (`baseline.md`).
- Instala com `uv`, sem Node nem `ffmpeg` embutidos.

## O que falta

| Área | Poach | AnyPoach hoje |
| --- | --- | --- |
| Captura | área, janela por prévia, tela cheia, screenshot, importar vídeo ou imagem | área, tela cheia, janela (v0.9.0; sem macOS), screenshot e importar vídeo ou imagem (v0.6.0) |
| Controle | atalho que liga e desliga, ícone na barra de menu, sombra na área, janelas próprias fora do vídeo | botões na janela; janelas próprias fora do vídeo |
| Editor | comentários presos à timeline, paleta ajustável, instruções gerais | comentários, timeline, play e instruções gerais (v0.3.0); paleta ajustável (v0.8.0) |
| Entrega | "Continue com Codex/Claude Code" abre o app e copia o prompt | só copia o prompt |
| Conector MCP | instalador do Codex e extensão `.mcpb` | `anypoach-setup` imprime o comando do Claude Code, do Codex ou JSON; sem `.mcpb` |
| Extras | favoritos `.poach`, "Snatch font", limpeza de armazenamento, atualização, onboarding | limpeza e atualização sob demanda (v0.7.0) e favoritos (v0.10.0); falta Snatch font; onboarding (v0.11.0) |
| Chrome | extensão com estilos computados, eventos e tempos de animação | extensão própria na v0.2.0 (porta 47832, sem loja): estilos, animações, eventos, cartão do inspetor e componentes filhos |
| Distribuição | `.zip` pronto | instalação por `uv` |
| Ponteiro | macOS | Windows, X11 e macOS (Wayland sem trace; macOS só testado com fakes e CI até alguém rodar o spike) |

## O que o Poach também não resolve

- As imagens vão reduzidas a 1280 px sem informar a escala (`extractor.ts`, `maxSize = 1280`).
- Uma só estimativa de timing cobre o vídeo todo, mesmo com várias interações; o próprio documento de fidelidade avisa que lê-la como a duração de uma interação dá resultado errado.
- A precisão de tamanho e tipografia de interfaces web vem da extensão do Chrome (`width`, `height`, `fontSize`, `lineHeight`, `borderRadius`...), não do vídeo.

## Roteiro de releases

Proposta, a confirmar. A versão do pacote e a da extensão sobem juntas (um teste garante). Todas ficam como pré-release até a 1.0, e tag e release só saem quando o usuário manda.

| Versão | Conteúdo | Estado |
| --- | --- | --- |
| v0.1.0 | Tamanho e escala da captura no brief e nas legendas; captura no Wayland | publicada (pré-release) |
| v0.2.0 | Extensão do Chrome (PR #3) e inspetor de página: cartão ao passar o mouse e medidas dos componentes filhos | publicada (pré-release) |
| v0.2.1 | macOS: ponteiro por CoreGraphics, regiões Retina e aviso de permissão de gravação de tela | publicada (pré-release); spike e checagens manuais num Mac ainda não rodados |
| v0.3.0 | Trechos de movimento (várias interações por gravação) e editor com comentários, instruções gerais e timeline | publicada (pré-release) |
| v0.3.1 | Botão de tela cheia (um clique, sem arrastar) | publicada (pré-release) |
| v0.4.0 | Bandeja permanente com menu (mostrar, gravar tela cheia, sair; parar durante a gravação) | publicada (pré-release) |
| v0.5.0 | `anypoach-setup` (comandos do Claude Code, do Codex e JSON) e instalação por `uv tool install` sem clonar | publicada (pré-release) |
| v0.6.0 | Alcance do Poach de 2026-11-21: `pageRect`, screenshot da área e importação de vídeo ou imagem | publicada (pré-release) |
| v0.7.0 | Janela de configurações: armazenamento e limpeza, comandos do Claude Code e do Codex, verificação de atualização sob demanda (decisão de produto: exceção à promessa de não usar rede) | publicada (pré-release) |
| v0.8.0 | Paleta ajustável (trocar, tirar, acrescentar e restaurar cores; o brief leva a versão editada) | publicada (pré-release) |
| v0.9.0 | Modo janela: lista de janelas no X11 e no Windows, seletor do portal no Wayland (sem miniaturas e sem seguir a janela; macOS de fora) | publicada (pré-release) |
| v0.10.0 | Favoritos: salvar o handoff, copiar um novo prompt, exportar e importar `.anypoach` (formato próprio, validado com rigor; sem vídeo) | publicada (pré-release) |
| v0.11.0 | Onboarding: boas-vindas com a exigência do sistema e passo opcional de pareamento do Chrome; reabre em Settings | pronta; checagem manual pendente |
| v0.12.0+ | Resto do Poach, nesta ordem: atalho global opcional (desligado por padrão, exceção à promessa de não usar hooks), Snatch font, instalador sem `uv`, `.mcpb`, modo janela no macOS | não começou |

O Poach resolve tudo isso apenas para quem tem um Mac, o que continua sendo um recorte de público impressionante.
