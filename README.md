<div align="center">

<img src="assets/banner.svg" alt="HoraInfo — Network monitoring for Home Assistant" width="100%">

# HoraInfo

[![Offline validation](https://github.com/lucaslucian/ha_oraco/actions/workflows/offline-tests.yml/badge.svg)](https://github.com/lucaslucian/ha_oraco/actions/workflows/offline-tests.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom%20Repository-41BDF5?logo=homeassistant&logoColor=white)](https://github.com/lucaslucian/ha_oraco#instala%C3%A7%C3%A3o)
[![License: MIT](https://img.shields.io/github/license/lucaslucian/ha_oraco)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/lucaslucian/ha_oraco?include_prereleases&label=release)](https://github.com/lucaslucian/ha_oraco/releases)
[![Latest commit](https://img.shields.io/github/last-commit/lucaslucian/ha_oraco)](https://github.com/lucaslucian/ha_oraco/commits/main)

**Monitoramento de switches gerenciáveis para Home Assistant**

</div>

Integração experimental **somente leitura** para monitorar switches Horaco e OEM com interface CGI Realtek no Home Assistant. A integração usa HACS e registra um painel na barra lateral, sem Docker ou Lovelace customizado.

## Estado do desenvolvimento (0.4.1 — experimental)

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
| VLAN/PVID/Port Isolation completos | Não | Precisa identificar endpoints |
| Alertas sofisticados e limites ópticos | Não | Exigem limiares do módulo |
| Mapa visual arrastável / LLDP | Não | LLDP depende de suporte real |
| Configuração do switch | Não | Não está prevista nesta fase |

O painel expõe visão geral, portas, SFP+, dispositivos, VLANs (estado pendente), mapa lógico e sistema. O grafo MAC demonstra **aprendizado na porta**, não a conexão física direta. Não representa hosts atrás de NAT individualmente.

## Instalação

1. HACS → Repositórios personalizados → adicionar `https://github.com/lucaslucian/ha_oraco` como **Integração**.
2. Instalar, reiniciar o Home Assistant.
3. Configurações → Dispositivos e serviços → Adicionar integração → **HoraInfo**.
4. Informar host, porta HTTP, usuário e senha.
5. Após configurar, verificar a entrada **HoraInfo** na barra lateral. O painel detalhado exige usuário administrador.

## Atualização e coleta

- Portas, tráfego: 30 segundos (ajustável no fluxo de opções).
- Transceptores: 60 segundos.
- Tabela MAC: 120 segundos.
- DHCP/IGMP: 300 segundos.
- Jumbo frames: 3600 segundos.
- Informações gerais publicadas: 3600 segundos. Como `/info.cgi` também fornece os estados das portas, ele é consultado a cada ciclo rápido.
- IEEE OUI: arquivo em cache persistente e verificação de atualização após 30 dias, no início da integração.

A integração descobre automaticamente as interfaces e os recursos disponíveis em cada equipamento compatível.

## Privacidade e segurança

- Nenhum endpoint de alteração de VLAN, reset, atualização, reboot ou controle administrativo.
- O cliente usa GET nas rotas de monitoramento aprovadas. POST ocorre somente em login e paginação de leitura da tabela MAC.
- Painel e WebSocket restritos a administradores.
- O inventário MAC (até 2.000 identidades por switch) é armazenado localmente; não é enviado à IEEE. O download de registros IEEE é separado das consultas MAC.
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
