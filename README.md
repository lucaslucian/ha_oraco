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

## Estado do desenvolvimento (0.4.9 — experimental)

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

O painel expõe visão geral, portas, SFP+, dispositivos, VLANs (estado pendente), mapa lógico e sistema. O grafo MAC demonstra **aprendizado na porta**, não a conexão física direta. Não representa hosts atrás de NAT individualmente.

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
- Versão do firmware: leitura GET de `/fwug.cgi` a cada 6 horas, sem comandos de atualização.
- Jumbo frames: 3600 segundos.
- Informações gerais publicadas: 3600 segundos. Como `/info.cgi` também fornece os estados das portas, ele é consultado a cada ciclo rápido.
- IEEE OUI: arquivo em cache persistente e verificação de atualização após 30 dias, no início da integração.

A integração descobre automaticamente as interfaces e os recursos disponíveis em cada equipamento compatível.

Os picos de tráfego RX/TX são calculados para o switch inteiro e por interface a partir das taxas observadas e armazenadas no SQLite. O histórico de amostras é mantido por 14 dias e os picos representam esse período. A visão geral exibe a série recente do switch, e a aba Portas permite selecionar uma interface para consultar seu histórico gráfico. O gráfico usa o banco, inclusive após recarregar a página ou reiniciar a integração. Observações anteriores à instalação desta versão não podem ser recuperadas retroativamente. O inventário mantém em SQLite o fabricante atribuído, VLAN, porta, classificação e datas da primeira e da última observação de cada MAC. A atualização da base IEEE revalida os fabricantes históricos e atuais, inclusive registros antigos retidos no SQLite. Os três arquivos IEEE são verificados separadamente; falhas preservam os prefixos já conhecidos e uma nova tentativa é agendada diariamente quando a atualização estiver pendente. A aba Sistema mostra a quantidade de prefixos, a data da última atualização e o status de cada origem. Mudanças em SFP, VLAN, STP, isolamento, Storm Control e agregação são registradas como snapshots por até 90 dias; amostras inalteradas não são duplicadas. Para evitar crescimento excessivo, os snapshots SFP são limitados a um registro a cada cinco minutos. A aba Sistema apresenta os eventos recentes detectados. O armazenamento anterior do inventário MAC em Home Assistant Store é usado para migração, sem apagar dados históricos.

O mapa da rede exibe conexões lógicas MAC–porta (sem afirmar que os dispositivos estão diretamente ligados ao switch).

## Privacidade e segurança

- Nenhum endpoint de alteração de VLAN, reset, atualização, reboot ou controle administrativo.
- A página `/fwug.cgi` é consultada exclusivamente com GET para obter a versão. O comando `enter_loader`, que inicia a atualização do firmware, **nunca é enviado**.
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
