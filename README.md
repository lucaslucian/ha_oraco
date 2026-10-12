<div align="center">

<img src="assets/banner.svg" alt="HoraInfo — Network monitoring for Home Assistant" width="100%">

# HoraInfo

[![Offline validation](https://github.com/lucaslucian/ha_oraco/actions/workflows/offline-tests.yml/badge.svg)](https://github.com/lucaslucian/ha_oraco/actions/workflows/offline-tests.yml)
[![License: MIT](https://img.shields.io/github/license/lucaslucian/ha_oraco)](LICENSE)
[![Latest commit](https://img.shields.io/github/last-commit/lucaslucian/ha_oraco)](https://github.com/lucaslucian/ha_oraco/commits/main)

**Monitoramento de switches gerenciáveis para Home Assistant**

[![Adicionar ao HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=lucaslucian&repository=ha_oraco&category=integration)

</div>

Integração experimental **somente leitura** para monitorar switches Horaco e OEM com interface CGI Realtek no Home Assistant. A integração usa HACS e registra um painel na barra lateral, sem Docker ou Lovelace customizado.

## Estado do desenvolvimento (0.4.21 — experimental)

| Função | Implementação | Requer validação no switch |
|---|---|---|
| Portas, link, duplex, RX/TX e taxas | Sim | Sim |
| Painel integrado, visual escuro/claro | Sim | Teste real no HA |
| MAC table, múltiplas páginas e histórico | Sim | Sim |
| Classificação MAC local/privado | Sim | Testável offline |
| Fabricante OUI (IEEE MA-L/M/S) | Sim, cache local e atualização quando necessário | Teste de download no HA |
| Topologia MAC por porta | Sim, modelo lógico | Sim |
| SFP DDMI (RX, TX, temperatura e tensão) | Sim, parser do firmware de referência | Sim |
| IGMP e DHCP Snooping | Sim | Sim |
| Jumbo Frames | Sim | Sim |
| VLAN por porta (Access/Trunk/Hybrid, Native, tagged/untagged) | Sim, leitura somente GET | Sim, depende do firmware | 
| Port Isolation — listas por porta | Sim, somente leitura | Sentido exato da lista depende do firmware |
| STP por porta — estado, role, path cost, P2P e Edge | Sim, somente leitura | Sim |
| Storm Control — limites por porta | Sim, somente leitura | Sim |
| PVID completo | Não | Exige identificação de endpoints adicionais |
| Alertas sofisticados e limites ópticos | Não | Exigem limiares do módulo |
| Mapa visual arrastável / LLDP | Não | LLDP depende de suporte real |
| Configuração do switch | Não | Não está prevista nesta fase |

O painel expõe visão geral, portas, **Histórico**, SFP+, dispositivos, VLANs, proteções, mapa lógico e sistema. O grafo MAC demonstra **aprendizado na porta**, não a conexão física direta. Não representa hosts atrás de NAT individualmente.

## Instalação

### Instalação pelo HACS

Clique no botão **Adicionar ao HACS** acima para abrir este repositório no HACS da sua instância do Home Assistant. Caso ainda não esteja cadastrado, adicione-o como repositório personalizado na categoria **Integração**.

### Instalação manual

1. Baixe os arquivos deste repositório e copie a pasta `custom_components/ha_oraco` para `<config>/custom_components/ha_oraco` no Home Assistant, preservando os arquivos internos.
2. Reinicie o Home Assistant.
3. Acesse **Configurações → Dispositivos e serviços → Adicionar integração → HoraInfo**.
4. Informe o endereço do switch, porta HTTP, usuário e senha.
5. Abra **HoraInfo** na barra lateral. O painel de inventário requer uma conta administradora.

A instalação manual não recebe as atualizações automáticas do HACS.

## Atualização e coleta

- Portas, tráfego: 30 segundos (ajustável no fluxo de opções).
- Transceptores: 60 segundos.
- Tabela MAC: 120 segundos.
- DHCP/IGMP: 300 segundos.
- VLAN por porta: 600 segundos, somente consulta da tabela de estado.
- Isolamento, STP por porta e Storm Control: 600 segundos, somente GET.
- Firmware, modelo, MAC e uptime: extraídos de `/info.cgi` (a mesma consulta de estado das portas). O endpoint `/fwug.cgi` não é consultado.
- Jumbo frames: 3600 segundos.
- Informações gerais publicadas: 3600 segundos. Como `/info.cgi` também fornece os estados das portas, ele é consultado a cada ciclo rápido.
- IEEE OUI: arquivo em cache persistente e verificação de atualização após 30 dias, no início da integração.

A integração descobre automaticamente as interfaces e os recursos disponíveis em cada equipamento compatível.

Os picos de tráfego RX/TX são calculados para o switch inteiro e por interface a partir das taxas observadas e armazenadas no SQLite. As amostras detalhadas são mantidas por 48 horas; médias e picos agregados a cada cinco minutos por até 30 dias. O usuário pode escolher períodos de 1, 6 ou 12 horas, 1, 3, 5, 7, 15 ou 30 dias. O volume acumulado de RX/TX é contabilizado por diferença positiva dos contadores de bytes reais em intervalos de cinco minutos, além de totais por dia, porta e switch. Amostras detalhadas e consolidados diários têm retenção máxima de 30 dias. O gráfico de barras mostra o volume diário RX/TX e o período selecionado mostra o volume acumulado. Reinícios da integração ou reset de contadores não geram volumes artificiais, embora possam deixar uma pequena lacuna. Os picos representam os últimos 30 dias. A visão geral e a aba Portas exibem somente o estado atual. A aba **Histórico** reúne gráficos de tráfego, volumes diários e seleção de interface e período em menus, até 30 dias. O gráfico usa o banco, inclusive após recarregar a página ou reiniciar a integração. Observações anteriores à instalação desta versão não podem ser recuperadas retroativamente. O inventário mantém em SQLite o fabricante atribuído, VLAN, porta, classificação e datas da primeira e da última observação de cada MAC. A atualização da base IEEE revalida os fabricantes históricos e atuais, inclusive registros antigos retidos no SQLite. Caso os endpoints IEEE sejam bloqueados pela rede ou proteção antibot, a integração tenta um espelho público dos prefixos MA-L, sem presumir suporte adicional a MA-M e MA-S nesse espelho. Os três arquivos IEEE são verificados separadamente; falhas preservam os prefixos já conhecidos e uma nova tentativa é agendada diariamente quando a atualização estiver pendente. A aba Sistema mostra a quantidade de prefixos, a data da última atualização e o status de cada origem. Leituras de SFP, VLAN, STP, isolamento, Storm Control e agregação recebem um resumo diário da data e quantidade de verificações, durante 90 dias. Somente alterações criam snapshots detalhados, evitando duplicação dos dados a cada coleta. Para evitar crescimento excessivo, os snapshots SFP são limitados a um registro a cada cinco minutos. A aba Sistema apresenta os eventos recentes detectados. Cada aba compatível tem um botão de histórico por dia, inclusive para indicar ausência de alterações. O armazenamento anterior do inventário MAC em Home Assistant Store é usado para migração, sem apagar dados históricos.

O mapa da rede representa cada MAC observado como um nó individual conectado à respectiva porta por vínculo lógico. O mapa exibe conexões lógicas MAC–porta (sem afirmar que os dispositivos estão diretamente ligados ao switch).

## Privacidade e segurança

- Nenhum endpoint de alteração de VLAN, reset, atualização, reboot ou controle administrativo.
- A página `/fwug.cgi` não é mais consultada. A versão é lida de `/info.cgi`, sem acesso ao endpoint de atualização do firmware.
- O cliente usa GET nas rotas de monitoramento aprovadas. POST ocorre somente em login e paginação de leitura da tabela MAC.
- Painel e WebSocket restritos a administradores.
- O inventário MAC (cache Store limitado a 2.000 identidades por switch e histórico ampliado no SQLite) é armazenado localmente no Home Assistant; não é enviado à IEEE. O download de registros IEEE é separado das consultas MAC. O arquivo SQLite é criado em `.storage/ha_oraco_history.db` e deve ser incluído nos backups para preservar o histórico.
- MAC com bit local é rotulado **MAC local/privado**, não necessariamente aleatorizado.
- O diagnóstico exportável omite credenciais e endereços MAC. O equipamento pode usar HTTP sem TLS; utilize somente em rede confiável.
- A recuperação da sessão depende do firmware. Não exponha a interface de administração do switch à internet.

## Testes sem hardware

```bash
python -m pip install beautifulsoup4 pytest
python -m compileall -q custom_components/ha_oraco
python -m pytest -q tests/
node --check custom_components/ha_oraco/frontend/ha-oraco-panel.js
```

Simulador local:

```bash
python devtools/mock_switch.py --ports 10 --port 8089
```

O simulador atende `127.0.0.1:8089` com HTML de referência e não modifica equipamentos. Para conectar a partir do HA em contêiner será necessário configurar um host acessível **somente na rede de testes**. O simulador é de desenvolvimento; não replica todas as peculiaridades dos firmwares.

## Referências e créditos

Inspirado em [switch-dashboard](https://github.com/byte4geek/switch-dashboard) e [horaco_switch_ha](https://github.com/gtrancillo/horaco_switch_ha). Código desenvolvido com assistência de IA.

**Atenção:** código disponibilizado para testes, sem homologação num Horaco real. Os parsers e o painel precisam de validação no Home Assistant antes de considerar o projeto estável.


### Diagnóstico de dados ausentes

Se a página SFP+ não responder, o HoraInfo informa **diagnóstico indisponível**, e não módulo fisicamente ausente. A aba Sistema mostra o erro do endpoint SFP+, permitindo diferenciar problemas de parser, autenticação e rede. O painel é versionado para evitar o uso de JavaScript anterior no cache do navegador.


### Identidade visual e ícones

A integração fornece `brand/icon.png`, `brand/icon@2x.png`, `brand/logo.png` e `brand/logo@2x.png`, inclusive variações para tema escuro. São gerados a partir dos SVGs em `assets/` e utilizados localmente pelo Home Assistant 2026.3 ou posterior. O HACS pode continuar exibindo o placeholder **Icon not available** na lista de downloads ou na entidade de atualização devido à implementação atual de sua interface, que pode consultar o CDN antigo em vez dos ícones locais. Isso não indica ausência dos arquivos no HoraInfo. Após instalar uma nova versão pelo HACS, reinicie o Home Assistant para atualizar os recursos de marca.


### Integridade do histórico (0.4.16)

A migração de amostras antigas para intervalos de cinco minutos é executada uma única vez por arquivo SQLite, sem reimportar linhas em cada reinício. Os últimos contadores de bytes são preservados de forma temporária entre reinícios rápidos da integração (até três minutos) para evitar lacunas desnecessárias. Se o equipamento ficar indisponível por mais tempo ou reiniciar os próprios contadores, um novo ponto de referência é estabelecido sem inventar consumo durante a ausência. As atualizações do histórico MAC preservam as datas já conhecidas quando novas observações não as apresentam. Falhas na escrita do histórico ou reclassificação de fabricantes são isoladas do fluxo de monitoramento, e o diagnóstico indica o problema em vez de reportar falsamente a consulta como indisponível.

A partir da 0.4.17, a paginação da tabela MAC também renova uma sessão HTTP expirada uma única vez, e a falha ao salvar o cache legado não é interpretada como falha de coleta. Em caso de indisponibilidade do banco, o HoraInfo mantém o monitoramento e registra o erro para diagnóstico.


### Proteção de contadores de tráfego (0.4.19)

As amostras RX/TX são aceitas somente quando os contadores de bytes são válidos (inteiros de 64 bits), o tempo entre coletas é positivo e não ultrapassa 120 segundos e a diferença cabe na velocidade física negociada da porta (com margem de 25%). Saltos acima do limite, contadores zerados/reiniciados, possível rollover ou falhas de coleta não geram picos nem volume fictício: um novo valor de referência é estabelecido para a próxima amostra. RX e TX são validados separadamente, para que um problema em uma direção não invalide a outra. O banco SQLite aplica independentemente a mesma regra e mantém a última referência mesmo quando a primeira coleta ainda não permite calcular uma velocidade. Os contadores de eventos rejeitados ficam em `diagnostics.traffic_counters` para diagnóstico. Não é possível recuperar com exatidão o volume entre leituras interrompidas ou contadores reiniciados, e essas lacunas não são estimadas.


### Correções de compatibilidade OEM (0.4.20)

Algumas revisões do firmware fecham etiquetas `<th>` usando `</td>` e apresentam a primeira linha do transceptor sem `<tr>` inicial. Os parsers de `/info.cgi` e `/transceiver.cgi` agora extraem os pares de campos do HTML original com tolerância a esse formato, preservando modelo, firmware, uptime, MAC e informações do módulo óptico. O subtítulo do equipamento foi movido para abaixo do nome HoraInfo no cabeçalho. A suíte automatizada inclui casos de regressão baseados nessas respostas reais.


### Histórico em modal e MACs locais (0.4.21)

Os registros das configurações e proteções agora são abertos em janela modal com navegação por dia, sem árvores de JSON deslocadas no painel. Em histórico migrado, a contagem exibida de alterações considera também eventos realmente presentes no banco. O sensor **MACs privados (atuais)** conta endereços MAC com bit de administração local entre as observações atuais; **MACs privados (histórico)** conta esses endereços retidos no SQLite. Valores zero são legítimos quando os dispositivos observados usam MACs universalmente administrados.
