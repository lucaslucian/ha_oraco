<div align="center">

<img src="assets/banner.svg" alt="HoraInfo — monitoramento de switches no Home Assistant" width="100%">

# HoraInfo

**Monitoramento local de switches Horaco/OEM gerenciáveis no Home Assistant**

[![Testes, HACS e Hassfest](https://github.com/lucaslucian/ha_oraco/actions/workflows/offline-tests.yml/badge.svg)](https://github.com/lucaslucian/ha_oraco/actions/workflows/offline-tests.yml)
[![Licença MIT](https://img.shields.io/github/license/lucaslucian/ha_oraco)](LICENSE)
[![Último commit](https://img.shields.io/github/last-commit/lucaslucian/ha_oraco)](https://github.com/lucaslucian/ha_oraco/commits/main)

[![Adicionar ao HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=lucaslucian&repository=ha_oraco&category=integration)

</div>

> [!IMPORTANT]
> **Versão atual: 0.4.22 · Experimental · Somente leitura.**
> A integração já está sendo utilizada com um switch real e coleta dados no Home Assistant. Isso **não equivale a homologação universal**: o firmware e o HTML CGI variam entre modelos. Consulte as [limitações](#limitações-conhecidas) antes de instalar.

## O que é o HoraInfo?

O **HoraInfo** é uma integração personalizada para acompanhar switches Horaco e equipamentos OEM compatíveis com a interface HTTP/CGI utilizada por alguns switches gerenciáveis Realtek. Reúne dados de portas, tráfego, transceptor óptico, tabela MAC, VLANs e proteções em um **painel próprio na barra lateral**, além de disponibilizar **sensores e sensores binários nativos** do Home Assistant.

A comunicação é local e a integração é destinada a **monitoramento**, não ao gerenciamento da configuração do switch. Não modifica VLANs, isolamento de portas, STP, firmware ou parâmetros administrativos.

O nome apresentado é **HoraInfo**, mas o domínio interno da integração permanece `ha_oraco` para preservar a compatibilidade com instalações existentes. O endereço do repositório também permanece `lucaslucian/ha_oraco`.

## Funcionalidades

| Área | Recursos disponíveis |
| --- | --- |
| **Visão geral** | Portas ativas, taxas atuais RX/TX, picos observados, firmware e visão das interfaces |
| **Portas** | Estado do link, velocidade negociada, duplex, contadores de bytes e pacotes, taxas RX/TX por interface |
| **Histórico de tráfego** | Seleção do switch ou de uma porta; períodos de 1 h, 6 h, 12 h, 1, 3, 5, 7, 15 e 30 dias; gráfico de taxas e barras de volume diário |
| **SFP+ / DDMI** | Presença, tipo, fabricante, part number, número de série, temperatura, tensão, corrente, potência óptica e outros dados, conforme o módulo e o firmware |
| **Inventário MAC** | MACs aprendidos, porta, VLAN, classificação, fabricante quando disponível, primeira e última observação |
| **Mapa de rede** | Nós individuais por MAC e associações observadas com portas, usando nome conhecido ou fabricante quando disponíveis |
| **VLANs** | Informações de associação e modo das portas (access, trunk ou hybrid), VLAN nativa e listas tagged/untagged quando expostas pelo firmware |
| **Proteções** | Consulta de isolamento, STP/RSTP global e por porta, Storm Control e agregação de portas |
| **Outros diagnósticos** | IGMP, DHCP Snooping, Jumbo Frames, saúde das consultas HTTP e estado da base de fabricantes |
| **Home Assistant** | Sensores e sensores binários nativos, descoberta de interfaces e painel acessível a administradores |

O painel separa **estado atual** e **histórico**. As seções compatíveis possuem um visualizador de alterações em janela modal, organizado por dia, com verificações registradas e detalhes das mudanças.

### Mapa e identificação dos dispositivos

Cada endereço MAC observado na tabela de encaminhamento é representado individualmente. O HoraInfo pode apresentar o **nome conhecido** do registro, ou o **fabricante inferido pelo prefixo OUI**, ao lado do MAC.

**Fabricante não é nome de host:** a base IEEE/OUI não revela automaticamente nomes como `Notebook`, `OpenWrt` ou `HomeAssistant`. Também não há descoberta física por LLDP implementada. O mapa indica **em qual porta o switch aprendeu cada MAC**, mas não comprova que o dispositivo está conectado diretamente à porta — outros switches ou equipamentos podem existir no caminho.

### Sensores e classificação de MACs

Há sensores de informações do equipamento, quantidade de portas ativas, métricas ópticas, dados por porta e contagens de MACs.

Os sensores **MACs privados (atuais)** e **MACs privados (histórico)** representam endereços com o **bit de administração local** ativado. Um resultado igual a zero pode ser legítimo e não significa que não existam dispositivos na LAN. A contagem histórica utiliza o inventário persistido.

### Proteção contra contadores anômalos

As taxas RX/TX e os volumes acumulados são calculados a partir das diferenças entre contadores de bytes fornecidos pelo switch. O HoraInfo rejeita leituras inválidas, contadores reiniciados, possíveis rollovers, intervalos longos sem observação e variações incompatíveis com a capacidade da porta. RX e TX são avaliados separadamente.

**Tráfego durante períodos sem observação não é reconstruído nem estimado.** Após uma interrupção, pode haver lacunas no volume contabilizado. O objetivo é impedir picos artificiais e somas incorretas.

## Instalação

### Pelo HACS

Use **Adicionar ao HACS** no início desta página. Caso o redirecionamento não cadastre automaticamente o projeto:

1. Abra o **HACS** na sua instalação do Home Assistant.
2. Adicione `https://github.com/lucaslucian/ha_oraco` como **repositório personalizado**, categoria **Integração**.
3. Instale o **HoraInfo** e reinicie o Home Assistant.
4. Abra **Configurações → Dispositivos e serviços → Adicionar integração → HoraInfo**.
5. Informe **IP ou host, porta HTTP, usuário e senha** do switch.
6. Abra **HoraInfo** na barra lateral.

O HoraInfo é disponibilizado como **repositório personalizado do HACS**; o botão não significa que esteja incluído no catálogo oficial do HACS.

### Instalação manual (sem HACS)

1. Copie a pasta `custom_components/ha_oraco` deste repositório para `<config>/custom_components/ha_oraco` no Home Assistant.
2. Reinicie o Home Assistant.
3. Adicione a integração em **Configurações → Dispositivos e serviços**, como descrito acima.

Mantenha a pasta **`ha_oraco`** mesmo que a interface mostre o nome HoraInfo. Na instalação manual, as atualizações devem ser aplicadas manualmente.

### Atualização de instalações existentes

Atualize os arquivos pelo HACS ou pelo método manual utilizado, **reinicie o Home Assistant** e recarregue o navegador (`Ctrl + F5`) se o painel ainda mostrar a interface antiga. Mantenha um backup do diretório de configuração, especialmente do banco SQLite e do armazenamento local, antes de grandes atualizações.

## Coleta e armazenamento

O HoraInfo utiliza consultas HTTP periódicas. Os intervalos abaixo são os atualmente definidos no código; a coleta rápida pode ser ajustada nas opções da integração.

| Dados | Intervalo padrão |
| --- | --- |
| Informações de portas e contadores de tráfego | 30 s |
| SFP+ / transceptor | 60 s |
| Tabela MAC | 120 s |
| DHCP Snooping e IGMP | 5 min |
| VLANs, isolamento, STP, Storm Control e agregação | 10 min |
| Jumbo Frames | 60 min |
| Metadados estáticos do dispositivo | Publicação aproximadamente a cada 60 min; `/info.cgi` é consultado também no ciclo rápido |

As principais páginas utilizadas incluem `/info.cgi`, `/port.cgi?page=stats`, `/transceiver.cgi` e `/mac.cgi?page=fwd_tbl`, além dos endpoints específicos de VLANs e proteções.

A integração **reutiliza a sessão autenticada** enquanto válida e tenta recuperar sessões expiradas. POST é usado no login e na paginação de leitura da tabela MAC, sem comandos de configuração.

### Retenção e histórico SQLite

O banco fica em `<config>/.storage/ha_oraco_history.db`. É um banco **SQLite local**; não requer servidor externo.

| Tipo de registro | Política implementada |
| --- | --- |
| Amostras detalhadas de tráfego | Aproximadamente 48 horas |
| Médias e picos de tráfego em blocos de 5 minutos | 30 dias |
| Volumes RX/TX consolidados por dia e por interface | 30 dias |
| Resumos diários de verificações e snapshots de alterações | 90 dias |
| Inventário MAC: primeira/última observação, porta, VLAN e fabricante | Histórico persistente; sem retenção temporal automática definida no código |

O histórico de tráfego permite selecionar **1, 6 ou 12 horas; 1, 3, 5, 7, 15 ou 30 dias**. Volumes são derivados de **diferenças válidas dos contadores**, não da simples soma de velocidades instantâneas.

Os snapshots de VLANs, transceptores e proteções são gravados quando há alteração de dados, enquanto os resumos diários registram a última análise e a quantidade de verificações. A consulta é apresentada por dia em **janela modal**. As leituras ópticas têm limitação adicional para evitar excesso de snapshots.

Os dados antigos armazenados antes da instalação da funcionalidade de histórico não podem ser reconstruídos retroativamente. O HoraInfo possui procedimentos de migração do histórico compatível já existente.

### Fabricantes OUI

A integração tenta atualizar arquivos IEEE **MA-L, MA-M e MA-S**, mantém cache local e reclassifica identidades conhecidas quando novos prefixos são obtidos. Caso as fontes IEEE não respondam, há uma tentativa alternativa por espelho público de dados OUI, cuja cobertura pode ser menor.

A seção **Sistema → Base IEEE de fabricantes** permite verificar quantidade de prefixos disponíveis, última atualização e eventuais falhas. Um MAC pode continuar sem fabricante por indisponibilidade da base, ausência de correspondência ou por ser um endereço administrado localmente.

## Compatibilidade e limitações conhecidas

- **Experimental:** o projeto é utilizado com um switch real, mas não foi homologado em todos os equipamentos Horaco/OEM nem nas diferentes versões de firmware.
- **HTML CGI variável:** algumas páginas apresentam marcação HTML incorreta. Os parsers incluem tratamento para formatos já observados, mas outras variantes podem exigir ajustes.
- **Somente leitura:** não inclui ações de reboot, reset, atualização de firmware, mudança de VLAN, isolamento, STP ou outros parâmetros.
- **SFP+:** disponibilidade e precisão dos dados dependem do firmware, do módulo e da resposta da página óptica. Ausência de potência óptica **não implica necessariamente ausência física do módulo**.
- **Topologia:** não descobre automaticamente enlaces físicos ou nomes de host por LLDP, DHCP ou mDNS. Exibe evidências provenientes da tabela MAC.
- **VLANs:** não garante a descoberta de todas as configurações de PVID e recursos avançados do switch.
- **Alertas:** limites ópticos e alertas avançados ainda não estão implementados.
- **Ícones:** apesar de haver arquivos locais de marca em `custom_components/ha_oraco/brand/`, algumas telas do HACS ou a entidade de atualização podem exibir *Icon not available*; isso depende do mecanismo de resolução de ícones dessas interfaces.
- **Histórico:** em falhas de coleta ou reinicializações de contadores, pode haver intervalos não contabilizados; a integração não inventa valores para preencher essas lacunas.

Para investigar leituras ausentes, utilize **HoraInfo → Sistema → Saúde das consultas**. Ali é possível distinguir falhas HTTP, erros de interpretação do HTML e problemas de gravação do histórico.

## Segurança e privacidade

- Monitora o switch na rede local, sem expor endpoints de administração publicamente.
- O gerenciamento web desses equipamentos pode utilizar **HTTP sem TLS**; mantenha o switch em rede de administração confiável.
- Credenciais permanecem na configuração da integração do Home Assistant; o SQLite do HoraInfo **não armazena a senha do switch**.
- Os dados de MAC e histórico ficam na instalação local do Home Assistant. A consulta de fabricantes baixa **bases OUI**, sem enviar o inventário MAC individual à IEEE.
- O painel e os comandos WebSocket do dashboard/histórico exigem **usuário administrador**.
- Inclua `.storage/ha_oraco_history.db` e os dados pertinentes de `.storage/` nos backups do Home Assistant.

## Desenvolvimento e testes

O repositório possui testes automatizados de parsers, páginas CGI reais e malformadas, sessão HTTP, contadores de tráfego, SQLite, inventário e componentes do painel. O fluxo [Offline validation](https://github.com/lucaslucian/ha_oraco/actions/workflows/offline-tests.yml) executa **pytest, validação JavaScript/JSON, Hassfest e verificação HACS**. O indicador no topo reflete o resultado publicado pelo GitHub Actions; uma execução bem-sucedida não substitui os testes no hardware real.

Para executar localmente:

```bash
python -m pip install beautifulsoup4 aiohttp pytest
python -m compileall -q custom_components/ha_oraco devtools tests
python -m pytest -q tests/
node --check custom_components/ha_oraco/frontend/ha-oraco-panel.js
```

O simulador de desenvolvimento pode ser iniciado com:

```bash
python devtools/mock_switch.py --ports 10 --port 8089
```

O simulador escuta localmente e **não reproduz integralmente** o comportamento dos firmwares reais.

Para bugs e sugestões, utilize as [issues do GitHub](https://github.com/lucaslucian/ha_oraco/issues). Ao relatar problemas, informe a versão da integração, o modelo e o firmware do switch e os diagnósticos do painel, **sem compartilhar senhas ou cookies de autenticação**.

## Licença e créditos

Distribuído sob a [licença MIT](LICENSE).

Inspirado em [switch-dashboard](https://github.com/byte4geek/switch-dashboard) e [horaco_switch_ha](https://github.com/gtrancillo/horaco_switch_ha).

<sub>Partes do desenvolvimento e da documentação tiveram assistência de inteligência artificial. As funcionalidades e os limites de compatibilidade devem ser verificados em cada ambiente.</sub>
