# HA Oraco

Integração HACS **somente leitura** para switches Horaco/OEM compatíveis com a interface CGI Realtek.

## Estado: versão inicial 0.1.0 (experimental)

**Já implementado:** cadastro pelo fluxo de configuração, login HTTP, descoberta de portas por `/info.cgi`, velocidade/link/duplex, contadores de bytes e pacotes quando presentes na página, cálculo RX/TX em bit/s com base nos contadores reais, sensores nativos, informações de firmware/modelo/uptime e atualização operacional a cada 30 segundos. Um dispositivo pai representa o switch e dispositivos filhos representam as portas.

**Ainda não implementado:** tabela MAC, VLANs, Port Isolation, IGMP/DHCP Snooping, dados ópticos SFP+, dashboards avançados e atualização manual. Esses recursos exigem identificar e validar os endpoints de **consulta** específicos do firmware. Não foram criados dados fictícios.

## Instalação via HACS

1. HACS → menu de três pontos → **Repositórios personalizados**.
2. Adicione `https://github.com/lucaslucian/ha_oraco` como categoria **Integração**.
3. Instale **HA Oraco**, reinicie o Home Assistant.
4. Configurações → Dispositivos e serviços → Adicionar integração → **HA Oraco**.
5. Informe IP, porta HTTP, usuário e senha do switch.

O HA precisa acessar a interface web do switch. **Use uma rede local confiável**: a interface original de muitos modelos utiliza HTTP sem criptografia.

## Frequências previstas

| Dados | Intervalo desejado | Situação |
|---|---:|---|
| Link, velocidade e tráfego | 30 segundos | Implementado, configurável 15–300 s |
| SFP+ | 60 segundos | Pendente de endpoint |
| Tabela MAC | 2 minutos | Pendente de endpoint |
| IGMP/DHCP snooping | 5 minutos | Pendente de endpoint |
| VLANs e port isolation | 10 minutos | Pendente de endpoint |
| Informações gerais publicadas | 1 hora | Implementado (compartilha /info.cgi com links) |
| Modelo, firmware | 6 horas | Planejado cache separado |

**Importante:** /info.cgi também contém o estado das portas, portanto o HTML é lido a cada 30 s; apenas a publicação de metadados é desacelerada. O suporte efetivo depende de compatibilidade com o firmware, ainda não testada no seu equipamento.

## Segurança

Não existem métodos de reiniciar, alterar portas, aplicar VLAN, fazer reset ou atualizar firmware. Apenas o login exige POST, e o restante da coleta utiliza GET nas rotas explicitamente permitidas. Credenciais são armazenadas na configuração da integração pelo Home Assistant. A conta do switch pode continuar tendo permissões administrativas; somente o código da integração é read-only.

## Créditos

Inspirado pelo [horaco_switch_ha](https://github.com/gtrancillo/horaco_switch_ha) e pelo [switch-dashboard](https://github.com/byte4geek/switch-dashboard). Esta implementação inicial é independente, sem copiar diretamente seus arquivos. O projeto foi desenvolvido com auxílio de IA.
