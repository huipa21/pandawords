import { shallowRef } from 'vue'

const active = shallowRef<symbol>()
let audio: HTMLAudioElement | undefined
let fail: (() => void) | undefined
let generation = 0

export function useWordAudio() {
  return {
    active,
    stop(owner: symbol) {
      if (active.value !== owner)
        return
      audio?.pause()
      generation++
      active.value = undefined
      fail = undefined
    },
    async play(owner: symbol, src: string, onError: () => void) {
      audio ??= new Audio()
      audio.pause()
      const request = ++generation
      active.value = owner
      fail = onError
      audio.onended = () => {
        active.value = undefined
        fail = undefined
      }
      audio.onerror = () => {
        const notify = fail
        active.value = undefined
        fail = undefined
        notify?.()
      }
      audio.src = src
      try {
        await audio.play()
      }
      catch {
        if (active.value === owner && generation === request) {
          active.value = undefined
          fail = undefined
          onError()
        }
      }
    },
  }
}
