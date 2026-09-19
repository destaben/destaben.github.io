---
title: "Alertas que ayudan a decidir"
description: "Un criterio práctico para convertir señales técnicas en avisos que orientan una respuesta, en lugar de añadir ruido."
locale: es
pubDate: 2026-09-19
tags: [SRE, Observabilidad, Operación]
draft: false
---

Una alerta no es una gráfica con prisa. Es una petición de atención que interrumpe a alguien y debe justificar esa interrupción. La pregunta útil no es «¿podemos medirlo?», sino «¿qué decisión tomaremos cuando ocurra?».

## Empezar por el impacto

Una señal de CPU alta puede ser interesante; una alerta debería conectar esa señal con una consecuencia. Por ejemplo: «la tasa de errores supera el 2% durante diez minutos y ya afecta a una ruta crítica». El segundo caso da a la persona de guardia una prioridad, una ventana temporal y un lugar donde investigar.

Antes de crear un aviso, intento escribir una frase completa:

> Si esta condición se mantiene, el usuario o el equipo perderá una capacidad concreta y debemos hacer esta primera comprobación.

Si la frase no sale, quizá todavía tenemos una métrica para observar, no una alerta para atender.

## Tres piezas de contexto

Una alerta operativa gana mucho valor cuando incluye:

1. **Qué ha cambiado:** el servicio, la dependencia o el indicador que se ha desviado.
2. **A quién afecta:** el recorrido de usuario, la región o el equipo que nota el problema.
3. **Qué probar primero:** una consulta, un dashboard o una acción reversible que reduzca la incertidumbre.

No hace falta convertir cada aviso en un runbook enciclopédico. Un enlace al panel correcto y una primera hipótesis verificable suelen ser más útiles que una lista larga de posibilidades.

## Revisar el ruido como un fallo de diseño

Las alertas que nadie abre, las que se cierran sin mirar y las que llegan durante mantenimientos planificados enseñan algo del sistema. Conviene revisarlas con la misma calma que un incidente: ¿el umbral representa daño real?, ¿la ventana evita picos breves?, ¿la propiedad está clara?, ¿sigue siendo necesaria?

Reducir una alerta no es rebajar la vigilancia. Es reservar la atención humana para las señales que pueden cambiar el resultado de una situación.