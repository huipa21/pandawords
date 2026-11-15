import type { GlobalThemeOverrides } from 'naive-ui'
import type { ThemeMode } from './tokens'
import { layout, motion, radius, themes, typography } from './tokens'

function createNaiveTheme(mode: ThemeMode): GlobalThemeOverrides {
  const { colors, shadows } = themes[mode]
  return {
    common: {
      primaryColor: colors.primary,
      primaryColorHover: colors['primary-hover'],
      primaryColorPressed: colors['primary-pressed'],
      primaryColorSuppl: colors['primary-hover'],
      infoColor: colors.info,
      successColor: colors.success,
      warningColor: colors.warning,
      errorColor: colors.error,
      textColorBase: colors.text,
      textColor1: colors.text,
      textColor2: colors['text-muted'],
      textColor3: colors['text-disabled'],
      textColorDisabled: colors['text-disabled'],
      borderColor: colors.border,
      dividerColor: colors.divider,
      bodyColor: colors.bg,
      cardColor: colors['surface-raised'],
      modalColor: colors['surface-raised'],
      popoverColor: colors['surface-raised'],
      tableColor: colors.surface,
      fontFamily: typography.font.sans,
      fontFamilyMono: typography.font.mono,
      fontWeight: typography.weight.regular,
      fontWeightStrong: typography.weight.semibold,
      fontSize: typography.size.base,
      fontSizeMini: typography.size.xs,
      fontSizeTiny: typography.size.xs,
      fontSizeSmall: typography.size.sm,
      fontSizeMedium: typography.size.base,
      fontSizeLarge: typography.size.lg,
      fontSizeHuge: typography.size.xl,
      lineHeight: typography.lineHeight.normal,
      borderRadiusSmall: radius.sm,
      borderRadius: radius.md,
      heightSmall: layout.controlHeight.small,
      heightMedium: layout.controlHeight.medium,
      heightLarge: layout.controlHeight.large,
      boxShadow1: shadows[1],
      boxShadow2: shadows[2],
      cubicBezierEaseInOut: motion.easing.standard,
      cubicBezierEaseOut: motion.easing.decelerate,
    },
  }
}

export const themeOverrides = createNaiveTheme('light')
export const darkThemeOverrides = createNaiveTheme('dark')
