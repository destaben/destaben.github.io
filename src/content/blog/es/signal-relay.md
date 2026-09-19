---
title: "Reticulum: un punto de contacto directo"
description: "La arquitectura de una dirección Reticulum pública, una bandeja respetuosa con la privacidad y métricas operativas separadas."
locale: es
pubDate: 2026-09-19
tags: [Reticulum, SRE, Architecture]
draft: false
---

Una web estática y un nodo Reticulum resuelven problemas distintos. La web debe ser rápida y accesible; el nodo debe ser persistente, observable y estar protegido frente al abuso.

## Límites explícitos

Un navegador no es un cliente Reticulum. La web no debe ocultarlo ni convertir un formulario en un sustituto engañoso de la mensajería directa. Un servicio propio mantiene una única dirección de entrega con la implementación oficial de Reticulum.

## Arquitectura

1. GitHub Pages sirve el portfolio estático.
2. Un subdominio de laboratorio llegará a un bridge por un túnel saliente HTTPS/WSS.
3. El bridge conserva una identidad Reticulum persistente y recibe mensajes directos en su dirección de entrega.
4. El panel público comparte esa dirección y muestra sólo avisos de llegada sanitizados; Prometheus recibe las métricas operativas por separado.

El nodo y el bridge no forman parte de este repositorio. Mantenerlos separados evita que secretos, identidades criptográficas y configuración operativa acaben en un despliegue público estático.

## Criterio de lanzamiento

La bandeja omite deliberadamente el cuerpo, el título y la identidad del remitente. La retención es limitada y la monitorización se queda en Prometheus, en lugar de convertirse en un panel de estado público. Así el canal resulta útil sin revelar conversaciones privadas ni topología operativa.