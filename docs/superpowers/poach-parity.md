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
| Captura | área, janela por prévia, tela cheia, screenshot, importar vídeo ou imagem | área, tela cheia, janela (v0.9.0, macOS na v0.17.0), screenshot e importar vídeo ou imagem (v0.6.0) |
| Controle | atalho que liga e desliga, ícone na barra de menu, sombra na área, janelas próprias fora do vídeo | atalho opcional (Windows e X11), bandeja com menu, moldura na área (v0.16.0); janelas próprias fora do vídeo |
| Editor | comentários presos à timeline, paleta ajustável, instruções gerais | comentários, timeline, play e instruções gerais (v0.3.0); paleta ajustável (v0.8.0) |
| Entrega | "Continue com Codex/Claude Code" abre o app e copia o prompt | copia o prompt e tenta abrir o app (v0.16.0) |
| Conector MCP | instalador do Codex e extensão `.mcpb` | `anypoach-setup` imprime o comando do Claude Code, do Codex ou JSON; `.mcpb` (v0.14.0, ainda não instalado num Claude Desktop real) |
| Extras | favoritos `.poach`, "Snatch font", limpeza de armazenamento, atualização, onboarding | limpeza e atualização sob demanda (v0.7.0) e favoritos (v0.10.0); Snatch font sem OCR (v0.13.0) e onboarding (v0.11.0) |
| Chrome | extensão com estilos computados, eventos e tempos de animação | extensão própria na v0.2.0 (porta 47832, sem loja): estilos, animações, eventos, cartão do inspetor e componentes filhos |
| Distribuição | `.zip` pronto | `.zip` por sistema sem Python nem `uv` (v0.15.0, sem assinatura) e instalação por `uv` |
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
| v0.11.0 | Onboarding: boas-vindas com a exigência do sistema e passo opcional de pareamento do Chrome; reabre em Settings | publicada (pré-release) |
| v0.12.0 | Atalho global opcional (Ctrl+Alt+Shift+P, desligado por padrão): registra só o acorde com `RegisterHotKey` (Windows) ou `XGrabKey` (X11); Wayland e macOS ficam de fora | publicada (pré-release) |
| v0.13.0 | Snatch font à nossa maneira: arrastar sobre uma linha, dizer o que ela diz e ranquear as fontes instaladas pelo formato das letras (sem OCR); vai no brief como `visualFontMatch` | publicada (pré-release) |
| v0.14.0 | Extensão `.mcpb` para o Claude Desktop (tipo `uv` do MCPB), gerada por `tools/build_mcpb.py` e anexada à release; o servidor do pacote extraído foi iniciado à mão, falta instalar no Claude Desktop | publicada (pré-release) |
| v0.15.0 | Instalador sem `uv`: pasta do PyInstaller com a janela, o servidor MCP e o `anypoach-setup`, um zip por sistema com `SHA256SUMS.txt`, montados pela CI a cada tag (sem assinatura) | publicada (pré-release) |
| v0.16.0 | Moldura vermelha fora da área gravada (sem Wayland), menu da bandeja com escolher área, gravar a área e screenshot, e "Continuar com Claude/Codex" (copia o prompt e tenta abrir o app; esquemas `claude://` e `codex://` não verificados) | publicada (pré-release) |
| v0.17.0 | Modo janela no macOS (`CGWindowListCopyWindowInfo`; nomes de janela dependem da permissão de gravação de tela) | pronta; só o runner de macOS da CI exercitou a chamada real |
| v1.0.0 | Primeira versão estável: paridade de recursos com o Poach 1.0.0 exceto o que está nas issues #36 a #41; nenhuma pessoa rodou em desktop real (issue #12) | publicada |
| v1.1+ | Atalho global no macOS e no Wayland, detecção automática de texto na fonte, assinatura e pacotes nativos (issues #36, #37, #39, #40) | não começou |

O Poach resolve tudo isso apenas para quem tem um Mac, o que continua sendo um recorte de público impressionante.
