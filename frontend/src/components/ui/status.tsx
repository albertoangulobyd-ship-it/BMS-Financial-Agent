/*
 * El componente de estado del dueno ("Asi quiero las alertas"): una pastilla redondeada
 * con un punto de color que late. Es su codigo; solo se cambio lo que hacia falta, y por
 * que (paso 15):
 *
 * - Contraste: el texto de success, warning e info (green-600, orange-600 y blue-600 sobre
 *   su tinte del 10 %, en text-xs) no llegaba a 4,5:1 sobre los fondos de la app y axe
 *   fallaba. Medido en Chromium (canvas: el tinte compuesto sobre cada fondo de la app, de
 *   #f7f5f0 y #fbfaf7 a la cabecera de tabla #f2efe8, la barra lateral #efece5, #ebe7df y un
 *   menu #ffffff): green-600 2,40-2,93, orange-600 2,64-3,22, blue-600 3,84-4,66 (y
 *   green-700 3,69-4,50, orange-700 3,85-4,69: tampoco). Ahora el TEXTO es green-800
 *   (5,32-6,49), orange-800 (5,43-6,62) y blue-700 (5,00-6,07); el tinte, el borde y el
 *   punto son los del dueno. error ya usaba --destructive (5,21-6,39) y default
 *   text-muted-foreground sobre bg-muted (5,73): no cambian. El punto no lleva texto: lo
 *   dice la etiqueta, siempre. e2e/fixtures.ts vuelve a medir cada pastilla en cada pantalla.
 * - Movimiento: motion-reduce:before:animate-none en el punto, para que el latido se pare
 *   a quien pide menos movimiento. Que lata o no lo decide components/status-pill.tsx
 *   (solo lo que pide hacer algo ya); las pantallas no eligen variante ni latido.
 * - Las clases dark: valen desde el paso 16, con el tema oscuro de Aurora (el de por
 *   defecto): src/index.css ata la variante dark a la clase .dark que lib/theme.tsx pone en
 *   <html> (@custom-variant dark), nunca a prefers-color-scheme. Sin eso, Tailwind v4 las
 *   aplicaria con un Windows en modo oscuro aunque la persona hubiera elegido el claro, y el
 *   texto saldria en los tonos -400 sobre un fondo claro (menos de 2:1). En oscuro, el texto
 *   -400 sobre su tinte en las tarjetas pasa de 4,5:1; e2e/status.spec.ts y
 *   e2e/themes.spec.ts miden cada pastilla en los dos temas.
 * - radix-ui 1.6.7 (el Slot de asChild): sus @radix-ui/* son las mismas versiones que ya
 *   estaban en package-lock.json (react-slot 1.3.3, react-primitive 2.1.10...), asi que no
 *   duplica nada y el Slot es el mismo de @radix-ui/react-slot: lo construido no crece
 *   (vendor, gzip: 152.610 bytes antes, 152.488 despues).
 */
import { cva, type VariantProps } from "class-variance-authority";
import { Slot as SlotPrimitive } from "radix-ui";
import type * as React from "react";
import { cn } from "@/lib/utils";

const statusVariants = cva(
  "inline-flex w-fit shrink-0 items-center gap-1.5 overflow-hidden whitespace-nowrap rounded-full border px-2.5 py-1 font-medium text-xs transition-colors",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-muted text-muted-foreground **:data-[slot=status-indicator]:bg-muted-foreground",
        success:
          "border-green-500/20 bg-green-500/10 text-green-800 **:data-[slot=status-indicator]:bg-green-600 dark:text-green-400 **:data-[slot=status-indicator]:dark:bg-green-400",
        error:
          "border-destructive/20 bg-destructive/10 text-destructive **:data-[slot=status-indicator]:bg-destructive",
        warning:
          "border-orange-500/20 bg-orange-500/10 text-orange-800 **:data-[slot=status-indicator]:bg-orange-600 dark:text-orange-400 **:data-[slot=status-indicator]:dark:bg-orange-400",
        info: "border-blue-500/20 bg-blue-500/10 text-blue-700 **:data-[slot=status-indicator]:bg-blue-600 dark:text-blue-400 **:data-[slot=status-indicator]:dark:bg-blue-400",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

interface StatusProps
  extends VariantProps<typeof statusVariants>, React.ComponentProps<"div"> {
  asChild?: boolean;
}

function Status(props: StatusProps) {
  const { className, variant = "default", asChild, ...rootProps } = props;

  const RootPrimitive = asChild ? SlotPrimitive.Slot : "div";

  return (
    <RootPrimitive
      data-slot="status"
      data-variant={variant}
      {...rootProps}
      className={cn(statusVariants({ variant }), className)}
    />
  );
}

function StatusIndicator(props: React.ComponentProps<"div">) {
  const { className, ...indicatorProps } = props;

  return (
    <div
      data-slot="status-indicator"
      {...indicatorProps}
      className={cn(
        "relative flex size-2 shrink-0 rounded-full",
        "before:absolute before:inset-0 before:animate-ping before:rounded-full before:bg-inherit motion-reduce:before:animate-none",
        "after:absolute after:inset-[2px] after:rounded-full after:bg-inherit",
        className,
      )}
    />
  );
}

function StatusLabel(props: React.ComponentProps<"div">) {
  const { className, ...labelProps } = props;

  return (
    <div
      data-slot="status-label"
      {...labelProps}
      className={cn("leading-none", className)}
    />
  );
}

export { Status, StatusIndicator, StatusLabel, statusVariants };

export default Status;
