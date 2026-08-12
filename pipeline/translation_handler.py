from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from modules.utils.language_utils import to_canonical_language_name
from .cache_manager import CacheManager
from .story_memory_context import (
    combine_story_memory_contexts,
    prepare_story_memory_context,
    translator_supports_context,
)

if TYPE_CHECKING:
    from controller import ComicTranslate
    from modules.translation.context.request_context import StoryMemoryRequestContextService
    from .main_pipeline import ComicTranslatePipeline

logger = logging.getLogger(__name__)


def _make_translator(main_page, source_lang, target_lang):
    from modules.translation.processor import Translator

    return Translator(main_page, source_lang, target_lang)


def _set_upper_case(blk_list, upper_case):
    from modules.utils.translator_utils import set_upper_case

    set_upper_case(blk_list, upper_case)


class TranslationHandler:
    """Handles translation processing with caching support."""
    
    def __init__(
            self, 
            main_page: ComicTranslate, 
            cache_manager: CacheManager, 
            pipeline: ComicTranslatePipeline,
            request_context_service: StoryMemoryRequestContextService | None = None,
            translator_builder=None,
        ):
        
        self.main_page = main_page
        self.cache_manager = cache_manager
        self.pipeline = pipeline
        self.request_context_service = request_context_service
        self.translator_builder = translator_builder or _make_translator

    def _current_page_path(self):
        image_files = getattr(self.main_page, "image_files", [])
        page_index = getattr(self.main_page, "curr_img_idx", -1)
        if 0 <= page_index < len(image_files):
            return image_files[page_index]
        return None

    def _prepare_current_page_context(
            self,
            blocks,
            source_lang,
            target_lang,
            user_extra_context,
        ):
        page_path = self._current_page_path()
        image_states = getattr(self.main_page, "image_states", {})
        state = image_states.get(page_path, {}) if page_path else {}
        return prepare_story_memory_context(
            self.main_page,
            page_path=page_path,
            page_uuid=state.get("page_uuid") if isinstance(state, dict) else None,
            blocks=blocks,
            source_lang=source_lang,
            target_lang=target_lang,
            user_extra_context=user_extra_context,
            service=self.request_context_service,
        )

    def _prepare_visible_webtoon_context(
            self,
            visible_blocks,
            source_lang,
            target_lang,
            user_extra_context,
        ):
        """Assemble each physical page once while preserving one LLM request."""
        page_blocks = {}
        for block in visible_blocks:
            page_index = getattr(block, "_page_index", None)
            if isinstance(page_index, int):
                page_blocks.setdefault(page_index, []).append(block)

        prepared_contexts = []
        image_files = getattr(self.main_page, "image_files", [])
        image_states = getattr(self.main_page, "image_states", {})
        for page_index in sorted(page_blocks):
            if not 0 <= page_index < len(image_files):
                continue
            page_path = image_files[page_index]
            state = image_states.get(page_path, {})
            prepared_contexts.append(
                prepare_story_memory_context(
                    self.main_page,
                    page_path=page_path,
                    page_uuid=state.get("page_uuid") if isinstance(state, dict) else None,
                    blocks=page_blocks[page_index],
                    source_lang=source_lang,
                    target_lang=target_lang,
                    user_extra_context="",
                    service=self.request_context_service,
                )
            )

        return combine_story_memory_contexts(user_extra_context, prepared_contexts)

    def translate_image(self, single_block=False):
        source_lang = to_canonical_language_name(
            self.main_page.s_combo.currentText(),
            self.main_page.lang_mapping,
        )
        target_lang = to_canonical_language_name(
            self.main_page.t_combo.currentText(),
            self.main_page.lang_mapping,
        )
        if self.main_page.image_viewer.hasPhoto() and self.main_page.blk_list:
            settings_page = self.main_page.settings_page
            image = self.main_page.image_viewer.get_image_array()
            extra_context = settings_page.get_llm_settings()['extra_context']
            translator_key = settings_page.get_tool_selection('translator')

            upper_case = settings_page.ui.uppercase_checkbox.isChecked()

            translator = self.translator_builder(self.main_page, source_lang, target_lang)
            translation_context = extra_context
            story_memory_identity = None
            if translator_supports_context(translator):
                prepared_context = self._prepare_current_page_context(
                    self.main_page.blk_list,
                    source_lang,
                    target_lang,
                    extra_context,
                )
                translation_context = prepared_context.effective_context
                story_memory_identity = prepared_context.cache_identity
            
            # Get translation cache key
            translation_cache_key = self.cache_manager._get_translation_cache_key(
                image,
                source_lang,
                target_lang,
                getattr(translator, "configuration_fingerprint", translator_key),
                extra_context,
                story_memory_identity=story_memory_identity,
            )
            
            if single_block:
                blk = self.pipeline.get_selected_block()
                if blk is None:
                    return
                
                # Check if block already has translation to avoid redundant processing
                if hasattr(blk, 'translation') and blk.translation and blk.translation.strip():
                    return
                
                # Check if we have cached translation results for this image/translator/language combination
                if self.cache_manager._is_translation_cached(translation_cache_key):
                    # Check if block exists in cache and source text matches
                    cached_translation = self.cache_manager._get_cached_translation_for_block(translation_cache_key, blk)
                    if cached_translation is not None:  # Block was processed and source text matches
                        blk.translation = cached_translation
                        logger.info(f"Using cached translation result for block: '{cached_translation}'")
                        _set_upper_case([blk], upper_case)
                        return
                    else:
                        logger.info("Block not found in cache or source text changed, processing single block...")
                    
                    # If we reach here, need to process the block
                    single_block_list = [blk]
                    translator.translate(single_block_list, image, translation_context)
                    
                    # Update the cache with this new result using the cache manager's method
                    self.cache_manager.update_translation_cache_for_block(translation_cache_key, blk)
                    
                    logger.info(f"Processed single block and updated cache: '{blk.translation}'")
                    _set_upper_case([blk], upper_case)
                else:
                    # Run translation on all blocks and cache the results
                    logger.info("No cached translation results found, running translation on entire page...")
                    # Create a mapping between original blocks and their copies
                    all_blocks_copy = []
                    
                    for original_blk in self.main_page.blk_list:
                        copy_blk = original_blk.deep_copy()
                        all_blocks_copy.append(copy_blk)
                    
                    if all_blocks_copy:  
                        translator.translate(all_blocks_copy, image, translation_context)
                        # Cache using the original blocks to maintain consistent IDs
                        self.cache_manager._cache_translation_results(translation_cache_key, self.main_page.blk_list, all_blocks_copy)
                        cached_translation = self.cache_manager._get_cached_translation_for_block(translation_cache_key, blk)
                        blk.translation = cached_translation
                        logger.info(f"Cached translation results and extracted translation for block: {cached_translation}")
                    
                    _set_upper_case([blk], upper_case)
            else:
                # For full page translation, check if we can use cached results
                if self.cache_manager._can_serve_all_blocks_from_translation_cache(translation_cache_key, self.main_page.blk_list):
                    # All blocks can be served from cache with matching source text
                    self.cache_manager._apply_cached_translations_to_blocks(translation_cache_key, self.main_page.blk_list)
                    logger.info(f"Using cached translation results for all {len(self.main_page.blk_list)} blocks")
                else:
                    # Need to run translation and cache results
                    translator.translate(
                        self.main_page.blk_list,
                        image,
                        translation_context,
                    )
                    self.cache_manager._cache_translation_results(translation_cache_key, self.main_page.blk_list)
                    logger.info("Translation completed and cached for %d blocks", len(self.main_page.blk_list))
                
                _set_upper_case(self.main_page.blk_list, upper_case)

    def translate_image_with_context_workflow(self):
        """Compatibility wrapper for the retired sidecar Context Translate action."""
        self.translate_image()

    def translate_webtoon_visible_area(self, single_block=False):
        """Perform translation on the visible area in webtoon mode."""
        source_lang = to_canonical_language_name(
            self.main_page.s_combo.currentText(),
            self.main_page.lang_mapping,
        )
        target_lang = to_canonical_language_name(
            self.main_page.t_combo.currentText(),
            self.main_page.lang_mapping,
        )
        
        if not (self.main_page.image_viewer.hasPhoto() and 
                self.main_page.webtoon_mode):
            logger.warning("translate_webtoon_visible_area called but not in webtoon mode")
            return
        
        # Get the visible area image and mapping data
        visible_image, mappings = self.main_page.image_viewer.get_visible_area_image()
        if visible_image is None or not mappings:
            logger.warning("No visible area found for translation")
            return
        
        # Filter blocks to only those in the visible area and convert coordinates
        from pipeline.webtoon_utils import (
            filter_and_convert_visible_blocks,
            restore_original_block_coordinates,
        )

        visible_blocks = filter_and_convert_visible_blocks(
            self.main_page, self.pipeline, mappings, single_block
        )
        if not visible_blocks:
            logger.info("No blocks found in visible area")
            return
        
        # Perform translation on the visible image with filtered blocks
        settings_page = self.main_page.settings_page
        extra_context = settings_page.get_llm_settings()['extra_context']
        upper_case = settings_page.ui.uppercase_checkbox.isChecked()
        
        translation_context = extra_context
        try:
            translator = self.translator_builder(self.main_page, source_lang, target_lang)
            if translator_supports_context(translator):
                translation_context = self._prepare_visible_webtoon_context(
                    visible_blocks,
                    source_lang,
                    target_lang,
                    extra_context,
                )
            translator.translate(visible_blocks, visible_image, translation_context)
        finally:
            # Coordinate conversion is temporary UI state and must never leak
            # when context preparation or a provider call raises.
            restore_original_block_coordinates(visible_blocks)
        
        # Apply upper case if needed
        _set_upper_case(visible_blocks, upper_case)
        
        logger.info(f"Translation completed for {len(visible_blocks)} blocks in visible area")
